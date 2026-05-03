"""
Auth dependencies — FastAPI dependency injection for role-based access control.

Role hierarchy:  ADMIN > OPERATOR > VIEWER
  - get_current_user     → any authenticated user
  - require_active_user  → any active authenticated user
  - require_operator     → OPERATOR or ADMIN only
  - require_admin        → ADMIN only
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..models.user import UserRole
from ..persistence import postgres
from .jwt_utils import decode_access_token

# Bearer token scheme (reads "Authorization: Bearer <token>" header)
_bearer = HTTPBearer(auto_error=False)

# Role hierarchy for comparison
_ROLE_WEIGHT = {
    UserRole.VIEWER.value: 0,
    UserRole.OPERATOR.value: 1,
    UserRole.ADMIN.value: 2,
}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    """
    Extract and validate the current user from the Authorization header.
    Returns the UserTable ORM object.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await postgres.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def require_active_user(user=Depends(get_current_user)):
    """Reject disabled/inactive users."""
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact an administrator.",
        )
    return user


async def require_operator(user=Depends(require_active_user)):
    """Only OPERATOR or ADMIN can access this endpoint."""
    if _ROLE_WEIGHT.get(user.role, 0) < _ROLE_WEIGHT[UserRole.OPERATOR.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Operator or Admin role required.",
        )
    return user


async def require_admin(user=Depends(require_active_user)):
    """Only ADMIN can access this endpoint."""
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin role required.",
        )
    return user

"""
Auth router — signup, login, and current user endpoints.

First user to register automatically becomes ADMIN.
Subsequent users default to VIEWER role (admin can promote them).
"""

import bcrypt
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..models.user import UserLogin, UserResponse, UserRole, UserSignup
from ..persistence import postgres
from .jwt_utils import create_access_token
from .dependencies import get_current_user

logger = logging.getLogger("ims.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Register a new user")
async def signup(body: UserSignup):
    """
    Register a new user with name, email, password, and designation.
    The first user to register automatically becomes ADMIN.
    Subsequent users are assigned VIEWER role by default.
    """
    # Check if email already exists
    existing = await postgres.get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Determine role: first user = ADMIN, rest = VIEWER
    all_users = await postgres.list_all_users()
    role = UserRole.ADMIN.value if len(all_users) == 0 else UserRole.VIEWER.value

    # Hash password and create user
    password_hash = _hash_password(body.password)
    user = await postgres.create_user(
        full_name=body.full_name,
        email=body.email,
        password_hash=password_hash,
        designation=body.designation,
        role=role,
    )

    token = create_access_token(user.id, user.email)
    logger.info("New user registered: %s (%s) role=%s", user.full_name, user.email, role)

    return {
        "token": token,
        "user": UserResponse.model_validate(user).model_dump(),
    }


@router.post("/login", response_model=dict, summary="Login with email and password")
async def login(body: UserLogin):
    """Authenticate a user and return a JWT token."""
    user = await postgres.get_user_by_email(body.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account has been deactivated. Contact an administrator.",
        )

    token = create_access_token(user.id, user.email)
    logger.info("User logged in: %s (role=%s)", user.email, user.role)

    return {
        "token": token,
        "user": UserResponse.model_validate(user).model_dump(),
    }


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(current_user=Depends(get_current_user)):
    """Return the profile of the authenticated user."""
    return current_user

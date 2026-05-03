"""
Admin router — user management endpoints (ADMIN role only).

Jenkins-like capabilities:
  - List all users with roles
  - Change user roles (ADMIN, OPERATOR, VIEWER)
  - Enable/disable user accounts
  - Delete users
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.dependencies import require_admin
from ..models.user import UserResponse, UserRole, UserRoleUpdate, UserStatusUpdate
from ..persistence import postgres

logger = logging.getLogger("ims.admin")

router = APIRouter(prefix="/admin", tags=["Admin — User Management"])


@router.get("/users", response_model=list[UserResponse], summary="List all users")
async def list_users(admin=Depends(require_admin)):
    """List all registered users with their roles and status. Admin only."""
    users = await postgres.list_all_users()
    return users


@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
    summary="Change user role",
)
async def update_user_role(user_id: str, body: UserRoleUpdate, admin=Depends(require_admin)):
    """
    Change a user's role (ADMIN, OPERATOR, VIEWER).
    Admin cannot demote themselves.
    """
    # Prevent self-demotion
    if user_id == admin.id and body.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own role. Ask another admin.",
        )

    target = await postgres.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    updated = await postgres.update_user_role(user_id, body.role.value)
    logger.info("Admin %s changed role of %s to %s", admin.email, target.email, body.role.value)
    return updated


@router.patch(
    "/users/{user_id}/status",
    response_model=UserResponse,
    summary="Enable or disable a user account",
)
async def update_user_status(user_id: str, body: UserStatusUpdate, admin=Depends(require_admin)):
    """
    Enable or disable a user account. Disabled users cannot log in.
    Admin cannot disable themselves.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot disable your own account.",
        )

    target = await postgres.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    updated = await postgres.update_user_status(user_id, body.is_active)
    action = "enabled" if body.is_active else "disabled"
    logger.info("Admin %s %s user %s", admin.email, action, target.email)
    return updated


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user account",
)
async def delete_user(user_id: str, admin=Depends(require_admin)):
    """
    Permanently delete a user account.
    Admin cannot delete themselves.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account.",
        )

    target = await postgres.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    await postgres.delete_user(user_id)
    logger.info("Admin %s deleted user %s (%s)", admin.email, target.full_name, target.email)

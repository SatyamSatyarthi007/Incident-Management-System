"""
User model — SQLAlchemy table + Pydantic schemas.
Stores user credentials, designation, role, and active status.

Roles:
  ADMIN    — Full access: manage users, assign roles, create/transition/close incidents
  OPERATOR — Can create incidents, transition states, submit RCA
  VIEWER   — Read-only: can only view incidents and dashboard
"""

import enum
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from . import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


# ── SQLAlchemy ORM table ────────────────────────────────────────────────────

class UserTable(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    designation = Column(String(200), nullable=False, default="Engineer")
    role = Column(String(20), nullable=False, default=UserRole.VIEWER.value, server_default=UserRole.VIEWER.value)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ── Pydantic schemas (API layer) ────────────────────────────────────────────

class UserSignup(BaseModel):
    full_name: str
    email: str
    password: str
    designation: str = "Engineer"


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    designation: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserStatusUpdate(BaseModel):
    is_active: bool

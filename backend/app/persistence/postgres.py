"""
PostgreSQL persistence — async SQLAlchemy engine, session factory, and CRUD.

All write/read operations are wrapped with exponential-backoff retry to handle
transient failures common in containerised environments (e.g. container startup
ordering, connection pool exhaustion, transient network partitions).
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from asyncpg.exceptions import (
    ConnectionDoesNotExistError,
    InterfaceError,
    TooManyConnectionsError,
)
from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.exc import OperationalError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from ..models import Base
from ..models.rca import RCATable
from ..models.user import UserTable
from ..models.work_item import WorkItemTable
from .retry import with_retry

# PostgreSQL-specific retryable exceptions
_PG_RETRYABLE = (
    OperationalError,
    DBAPIError,
    ConnectionDoesNotExistError,
    InterfaceError,
    TooManyConnectionsError,
    ConnectionError,
    ConnectionRefusedError,
    TimeoutError,
    OSError,
)

# ── Engine & session factory ────────────────────────────────────────────────

engine = create_async_engine(settings.postgres_dsn, echo=False, pool_size=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose connection pool on shutdown."""
    await engine.dispose()


async def health_check() -> bool:
    """Return True if PostgreSQL is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        return True
    except Exception:
        return False


# ── WorkItem CRUD ────────────────────────────────────────────────────────────

@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def create_work_item(
    title: str,
    severity: str,
    source: str,
    debounce_key: str,
    created_by_id: str = None,
    created_by_name: str = None,
) -> WorkItemTable:
    """Insert a new work item (status defaults to OPEN)."""
    item = WorkItemTable(
        id=str(uuid4()),
        title=title,
        severity=severity,
        source=source,
        debounce_key=debounce_key,
        created_by_id=created_by_id,
        created_by_name=created_by_name or "system",
    )
    async with async_session() as session:
        session.add(item)
        await session.commit()
        await session.refresh(item)
    return item


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def get_work_item(item_id: str) -> Optional[WorkItemTable]:
    async with async_session() as session:
        return await session.get(WorkItemTable, item_id)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def list_work_items() -> list[WorkItemTable]:
    async with async_session() as session:
        result = await session.execute(
            select(WorkItemTable).order_by(WorkItemTable.created_at.desc())
        )
        return list(result.scalars().all())


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def find_by_debounce_key(key: str) -> Optional[WorkItemTable]:
    """Find an OPEN or INVESTIGATING work item with the given debounce key."""
    async with async_session() as session:
        result = await session.execute(
            select(WorkItemTable)
            .where(WorkItemTable.debounce_key == key)
            .where(WorkItemTable.status.in_(["OPEN", "INVESTIGATING"]))
            .order_by(WorkItemTable.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def increment_signal_count(item_id: str) -> None:
    async with async_session() as session:
        await session.execute(
            update(WorkItemTable)
            .where(WorkItemTable.id == item_id)
            .values(
                signal_count=WorkItemTable.signal_count + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def update_work_item_status(
    item_id: str,
    status: str,
    **extra_fields,
) -> Optional[WorkItemTable]:
    """Transition a work item to a new status."""
    values = {"status": status, "updated_at": datetime.now(timezone.utc)}
    values.update(extra_fields)
    async with async_session() as session:
        await session.execute(
            update(WorkItemTable).where(WorkItemTable.id == item_id).values(**values)
        )
        await session.commit()
        return await session.get(WorkItemTable, item_id)


# ── RCA CRUD ─────────────────────────────────────────────────────────────────

@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def create_rca(work_item_id: str, **fields) -> RCATable:
    rca = RCATable(id=str(uuid4()), work_item_id=work_item_id, **fields)
    async with async_session() as session:
        session.add(rca)
        await session.commit()
        await session.refresh(rca)
    return rca


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def get_rca_by_work_item(work_item_id: str) -> Optional[RCATable]:
    async with async_session() as session:
        result = await session.execute(
            select(RCATable).where(RCATable.work_item_id == work_item_id)
        )
        return result.scalar_one_or_none()


# ── User CRUD ────────────────────────────────────────────────────────────

@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def create_user(
    full_name: str,
    email: str,
    password_hash: str,
    designation: str = "Engineer",
    role: str = "VIEWER",
) -> UserTable:
    """Create a new user account."""
    user = UserTable(
        id=str(uuid4()),
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        designation=designation,
        role=role,
    )
    async with async_session() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def get_user_by_email(email: str) -> Optional[UserTable]:
    """Find a user by email address."""
    async with async_session() as session:
        result = await session.execute(
            select(UserTable).where(UserTable.email == email)
        )
        return result.scalar_one_or_none()


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def get_user_by_id(user_id: str) -> Optional[UserTable]:
    """Find a user by UUID."""
    async with async_session() as session:
        return await session.get(UserTable, user_id)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def list_all_users() -> list[UserTable]:
    """List all users ordered by creation date."""
    async with async_session() as session:
        result = await session.execute(
            select(UserTable).order_by(UserTable.created_at.asc())
        )
        return list(result.scalars().all())


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def update_user_role(user_id: str, role: str) -> Optional[UserTable]:
    """Update a user's role."""
    async with async_session() as session:
        await session.execute(
            update(UserTable).where(UserTable.id == user_id).values(role=role)
        )
        await session.commit()
        return await session.get(UserTable, user_id)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def update_user_status(user_id: str, is_active: bool) -> Optional[UserTable]:
    """Enable or disable a user account."""
    async with async_session() as session:
        await session.execute(
            update(UserTable).where(UserTable.id == user_id).values(is_active=is_active)
        )
        await session.commit()
        return await session.get(UserTable, user_id)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_PG_RETRYABLE)
async def delete_user(user_id: str) -> None:
    """Permanently delete a user."""
    async with async_session() as session:
        await session.execute(
            sa_delete(UserTable).where(UserTable.id == user_id)
        )
        await session.commit()

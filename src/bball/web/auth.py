"""Authentication and authorization handling."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .. import settings
from ..models import User
from ..repositories import UserRepository

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Represents the currently authenticated user."""

    user: User
    is_admin: bool = False

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def name(self) -> str:
        return self.user.name


DEFAULT_ADMIN_ID = "admin-001"


def _user_repo() -> UserRepository:
    """Return the user repository configured for the active backend."""
    return settings.get_repository_classes().user()


def create_default_admin() -> User:
    """Create (if missing) the default admin user used for local development."""
    admin = User(
        id=DEFAULT_ADMIN_ID,
        email="admin@localhost",
        auth_type="local",
        name="Administrator",
        role="admin",
    )
    repo = _user_repo()
    if repo.get(admin.id) is None:
        repo.save(admin)
    return admin


def get_user_by_id(user_id: str) -> User | None:
    """Get a user by ID from the configured backend."""
    return _user_repo().get(user_id)


def save_user(user: User) -> None:
    """Persist a user to the configured backend."""
    _user_repo().save(user)


def list_users() -> list[User]:
    """List all users from the configured backend."""
    return _user_repo().list()


def delete_user(user_id: str) -> bool:
    """Delete a user. Returns True if deleted, False if not found."""
    repo = _user_repo()
    if repo.get(user_id) is None:
        return False
    repo.delete(user_id)
    return True


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """Get the currently authenticated user from the request."""
    if not credentials:
        # For local development, fall back to the default admin user
        admin = get_user_by_id(DEFAULT_ADMIN_ID) or create_default_admin()
        return CurrentUser(user=admin, is_admin=True)

    token = credentials.credentials
    # In local development, token is the user ID
    user = get_user_by_id(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    return CurrentUser(user=user, is_admin=user.role == "admin")


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency to require admin role."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user

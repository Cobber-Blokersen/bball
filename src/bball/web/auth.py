"""Authentication and authorization handling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..models import User

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


# In-memory user store for local development. In production, this would use the database.
_users_store: dict[str, User] = {}


def create_default_admin() -> User:
    """Create a default admin user for local development."""
    admin = User(
        id="admin-001",
        email="admin@localhost",
        auth_type="local",
        name="Administrator",
        role="admin",
    )
    _users_store[admin.id] = admin
    return admin


def get_user_by_id(user_id: str) -> User | None:
    """Get a user by ID from the store."""
    return _users_store.get(user_id)


def save_user(user: User) -> None:
    """Save a user to the store."""
    _users_store[user.id] = user


def list_users() -> list[User]:
    """List all users."""
    return list(_users_store.values())


def delete_user(user_id: str) -> bool:
    """Delete a user. Returns True if deleted, False if not found."""
    if user_id in _users_store:
        del _users_store[user_id]
        return True
    return False


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    """Get the currently authenticated user from the request."""
    if not credentials:
        # For local development, use the admin user
        admin = _users_store.get("admin-001") or create_default_admin()
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

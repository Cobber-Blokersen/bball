"""Admin routes for managing users and their data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...models import User
from ..auth import CurrentUser, delete_user, get_user_by_id, list_users, require_admin, save_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserCreateRequest(BaseModel):
    """Request to create a new user."""

    email: str
    name: str
    role: str = "user"


class UserResponse(BaseModel):
    """Response containing user information."""

    id: str
    email: str
    name: str
    role: str


@router.get("/users", response_model=list[UserResponse])
async def list_all_users(current_user: CurrentUser = Depends(require_admin)) -> list[UserResponse]:
    """List all users (admin only)."""
    users = list_users()
    return [UserResponse(id=u.id, email=u.email, name=u.name, role=u.role) for u in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> UserResponse:
    """Create a new user (admin only)."""
    import uuid

    user = User(
        id=str(uuid.uuid4()),
        email=request.email,
        name=request.name,
        role=request.role if request.role in ("user", "admin") else "user",
        auth_type="local",
    )
    save_user(user)
    return UserResponse(id=user.id, email=user.email, name=user.name, role=user.role)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> UserResponse:
    """Get a specific user (admin only)."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(id=user.id, email=user.email, name=user.name, role=user.role)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> None:
    """Delete a user (admin only)."""
    if not delete_user(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    request: UserCreateRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> UserResponse:
    """Update a user's role (admin only)."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updated_user = User(
        id=user.id,
        email=request.email or user.email,
        name=request.name or user.name,
        role=request.role if request.role in ("user", "admin") else user.role,
        auth_type=user.auth_type,
    )
    save_user(updated_user)
    return UserResponse(id=updated_user.id, email=updated_user.email, name=updated_user.name, role=updated_user.role)

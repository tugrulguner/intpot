"""Advanced FastAPI app — user management with Body and multiple methods."""

import json
from typing import Optional

from fastapi import Body, FastAPI

app = FastAPI()


@app.post("/users")
def create_user(
    username: str = Body(..., description="Unique username"),
    email: str = Body(..., description="Email address"),
    role: str = Body("member", description="User role"),
) -> dict:
    """Create a new user account."""
    return {"username": username, "email": email, "role": role, "created": True}


@app.get("/users/{user_id}")
def get_user(user_id: str) -> dict:
    """Retrieve a user by their ID."""
    return {"user_id": user_id, "username": "example", "role": "member"}


@app.put("/users/{user_id}")
def update_user(
    user_id: str,
    email: Optional[str] = Body(None, description="New email address"),
    role: Optional[str] = Body(None, description="New role"),
) -> dict:
    """Update user fields."""
    changes = {}
    if email is not None:
        changes["email"] = email
    if role is not None:
        changes["role"] = role
    return {"user_id": user_id, "updated": changes}


@app.delete("/users/{user_id}")
def delete_user(user_id: str) -> dict:
    """Delete a user by their ID."""
    return {"user_id": user_id, "deleted": True}


@app.get("/users")
def list_users(
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List users with pagination."""
    return {"users": [], "limit": limit, "offset": offset, "total": 0}


@app.post("/users/bulk")
def bulk_create(
    payload: str = Body(..., description="JSON array of user objects"),
) -> dict:
    """Create multiple users from a JSON payload."""
    users = json.loads(payload)
    return {"created": len(users), "users": users}

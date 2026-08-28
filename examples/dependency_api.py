"""FastAPI app whose dependency injection is intentionally not convertible."""

from fastapi import Depends, FastAPI

app = FastAPI()


def get_current_user() -> dict:
    """Return the authenticated user for this example."""
    return {"username": "example", "role": "member"}


@app.get("/profile")
def read_profile(user: dict = Depends(get_current_user)) -> dict:
    """Return the authenticated user's profile."""
    return user

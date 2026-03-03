"""Example FastAPI app for testing conversions."""

from fastapi import FastAPI

app = FastAPI()


@app.post("/add")
def add(a: int, b: int) -> dict:
    """Add two numbers together."""
    return {"result": a + b}


@app.post("/greet")
def greet(name: str, greeting: str = "Hello") -> dict:
    """Greet someone by name."""
    return {"message": f"{greeting}, {name}!"}

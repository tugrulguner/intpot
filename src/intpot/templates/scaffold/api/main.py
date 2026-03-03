"""{{project_name}} - FastAPI app."""

from fastapi import FastAPI

app = FastAPI(title="{{project_name}}")


@app.get("/hello")
def hello(name: str = "world") -> dict:
    """Say hello."""
    return {"message": f"Hello, {name}!"}

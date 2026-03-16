"""{{project_name}} - FastAPI app."""

from fastapi import FastAPI

app = FastAPI(title="{{project_name}}")


@app.get("/hello")
def hello(name: str = "world") -> dict:
    """Say hello."""
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

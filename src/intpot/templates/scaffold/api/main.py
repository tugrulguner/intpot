"""{{project_name}} - FastAPI app."""

from fastapi import FastAPI

app = FastAPI(title="{{project_name}}")


@app.get("/hello")
def hello(name: str = "world") -> dict:
    """Say hello."""
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    import uvicorn

    # Loopback only. Change to "0.0.0.0" to expose this on the network.
    uvicorn.run(app, host="127.0.0.1", port=8000)

"""Example: write once, serve as CLI, API, or MCP.

Usage:
    intpot serve examples/universal_app.py --cli
    intpot serve examples/universal_app.py --api
    intpot serve examples/universal_app.py --mcp
    intpot eject examples/universal_app.py --to api
"""

from intpot import App

app = App("example")


@app.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@app.tool()
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name."""
    return f"{greeting}, {name}!"

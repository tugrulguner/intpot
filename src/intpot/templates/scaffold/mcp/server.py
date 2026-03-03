"""{{project_name}} - FastMCP server."""

from fastmcp import FastMCP

mcp = FastMCP("{{project_name}}")


@mcp.tool()
def hello(name: str = "world") -> str:
    """Say hello."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    mcp.run()

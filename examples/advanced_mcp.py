"""Advanced FastMCP server — note-taking tools with various param types."""

import hashlib
import json
from datetime import datetime

from fastmcp import FastMCP

mcp = FastMCP("notes-server")


@mcp.tool()
def create_note(title: str, body: str, tags: str = "") -> str:
    """Create a new note with a generated ID."""
    note_id = hashlib.md5(title.encode()).hexdigest()[:8]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    note = {
        "id": note_id,
        "title": title,
        "body": body,
        "tags": tag_list,
        "created": datetime.now().isoformat(),
    }
    return json.dumps(note, indent=2)


@mcp.tool()
def search_notes(query: str, max_results: int = 5) -> str:
    """Search notes by keyword in title or body."""
    results = [{"id": "abc123", "title": f"Match: {query}", "snippet": "..."}]
    return json.dumps(results[:max_results])


@mcp.tool()
async def summarize(note_ids: str) -> str:
    """Summarize multiple notes by their IDs (comma-separated)."""
    ids = [nid.strip() for nid in note_ids.split(",")]
    return json.dumps({"summarized": len(ids), "ids": ids})


@mcp.tool()
def export_all(format: str = "json") -> str:
    """Export all notes in the specified format."""
    if format == "json":
        return json.dumps({"notes": [], "count": 0})
    return "No notes found."


if __name__ == "__main__":
    mcp.run()

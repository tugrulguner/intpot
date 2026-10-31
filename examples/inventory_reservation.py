"""Inventory reservation MCP service; bounded source conversion example (unreleased)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("inventory")
STOCK_UNITS = 150
UNIT_PRICE = 12


def reservation_cost(quantity: int, packs: int) -> int:
    if quantity * packs > STOCK_UNITS:
        raise ValueError("reservation exceeds available stock")
    return quantity * packs * UNIT_PRICE


@mcp.tool()
def reserve_inventory(
    quantity: Annotated[int, Field(ge=1, le=100)],
    packs: Annotated[int, Field(ge=1, le=5)] = 1,
    receipt: str = "",
) -> dict:
    """Reserve a bounded number of inventory units without mutable server state."""
    cost = reservation_cost(quantity, packs)
    result = {"quantity": quantity, "packs": packs, "cost": cost}
    if receipt:
        Path(receipt).write_text(str(result), encoding="utf-8")
    return result

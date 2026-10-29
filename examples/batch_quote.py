"""A bounded batch-order CLI used by application_conformance.py.

Numeric-range conversion requires the unreleased source slice containing this example.
Run the original: python examples/batch_quote.py --quantity 3
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer()
UNIT_PRICE = 25


def quote_total(quantity: int, discount: int) -> int:
    subtotal = quantity * UNIT_PRICE
    if discount > subtotal:
        raise ValueError("discount exceeds subtotal")
    return subtotal - discount


@app.command()
def quote(
    quantity: int = typer.Option(..., min=1, max=10),
    discount: int = typer.Option(0, min=0),
    receipt: str = "",
):
    """Quote a bounded batch, optionally writing a receipt after validation."""
    total = quote_total(quantity, discount)
    if receipt:
        Path(receipt).write_text(str(total), encoding="utf-8")
    typer.echo(str(total))


if __name__ == "__main__":
    app()

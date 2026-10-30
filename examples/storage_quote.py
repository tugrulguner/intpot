"""A small HTTP storage-cost service for API-source conformance.

Run its native and generated consumers with api_application_conformance.py.
Conversion of the numeric validation requires this unreleased source slice.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query

app = FastAPI()
DAILY_RATE = 0.02
CAPACITY_GB = 20000


def storage_cost(size_gb: int, days: int, replicas: int) -> float:
    if size_gb * replicas > CAPACITY_GB:
        raise ValueError("replicated storage exceeds capacity")
    return round(size_gb * days * replicas * DAILY_RATE, 2)


@app.get("/storage-quote")
def storage_quote(
    size_gb: int = Query(..., ge=1, le=10000),
    days: int = Query(7, ge=1, le=365),
    replicas: int = Query(2, ge=1, le=3),
    receipt: str = "",
) -> dict:
    """Estimate storage cost within individual and replicated capacity limits."""
    cost = storage_cost(size_gb, days, replicas)
    result = {"cost": cost, "size_gb": size_gb, "days": days, "replicas": replicas}
    if receipt:
        Path(receipt).write_text(str(result), encoding="utf-8")
    return result

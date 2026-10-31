from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mcp_application_conformance_native_consumers(tmp_path):
    script = Path(__file__).parents[1] / "examples/mcp_application_conformance.py"
    run = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert set(report["interfaces"]) == {"source_mcp", "cli", "api"}
    expected = report["interfaces"]["source_mcp"]["valid_results"]
    assert expected == [
        {"quantity": 1, "packs": 1, "cost": 12},
        {"quantity": 25, "packs": 3, "cost": 900},
        {"quantity": 100, "packs": 1, "cost": 1200},
    ]
    for item in report["interfaces"].values():
        assert item["valid_results"] == expected and item["receipts_verified"]
        assert set(item["rejections"]) == {
            "below_minimum",
            "above_maximum",
            "invalid_packs",
            "invalid_type",
            "missing_required",
            "business_error",
        }

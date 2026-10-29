from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_roadmap_prioritizes_application_capability_over_coordinate_completion():
    root = Path(__file__).parents[1]
    text = (root / "ROADMAP.md").read_text()
    next_milestone = text.split("### The next milestone", 1)[1].split(
        "### Released diagnostic foundation", 1
    )[0]
    assert "Application-led conformance and capability growth" in next_milestone
    assert "previously broken useful case" in next_milestone
    assert "deferred supporting work" in next_milestone
    for relative in [
        "README.md",
        "website/src/content/docs/conversion-boundaries.md",
        "website/src/content/docs/schema-reference.md",
        "src/intpot/templates/skills/intpot-cli.md",
        "src/intpot/templates/skills/intpot-python.md",
    ]:
        section = (
            (root / relative)
            .read_text()
            .split("## Bounded numeric-range conversion (unreleased)", 1)[1]
            .split("\n## ", 1)[0]
        )
        assert "public v0.16.0 does not" in section
        assert "one-sided" in section and "Clamping" in section
        assert (
            "framework-specific" in section and "application_conformance.py" in section
        )


def test_batch_quote_executes_the_original_and_generated_interfaces(tmp_path):
    example = Path(__file__).parents[1] / "examples/application_conformance.py"
    result = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert set(report["interfaces"]) == {"source_cli", "generated_cli", "api", "mcp"}
    for interface in report["interfaces"].values():
        assert interface["valid_results"] == [25, 75, 225]
        assert set(interface["rejections"]) == {
            "below_minimum",
            "above_maximum",
            "negative_discount",
            "invalid_type",
            "business_error",
        }
        assert interface["receipts_verified"]
    assert report["business_scope"] == "bounded CLI quote, native generated interfaces"

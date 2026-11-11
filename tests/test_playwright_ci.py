"""Browser CI and production verification share preinstalled browser dependencies."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("workflow", ["website.yml", "deploy-website.yml"])
def test_browser_workflows_use_locked_prebuilt_image(workflow: str) -> None:
    lock = json.loads((ROOT / "website/package-lock.json").read_text())
    version = lock["packages"]["node_modules/@playwright/test"]["version"]
    text = (ROOT / ".github/workflows" / workflow).read_text()
    image = re.search(r"^      image: (\S+)$", text, re.MULTILINE)
    assert image is not None, "browser jobs must use the official prebuilt image"
    assert re.fullmatch(
        rf"mcr\.microsoft\.com/playwright:v{re.escape(version)}-noble@sha256:[0-9a-f]{{64}}",
        image.group(1),
    )
    assert "options: --init --shm-size=1g" in text
    assert "playwright install" not in text
    assert "apt-get" not in text
    assert "- run: npm ci" in text
    assert "- run: npm run build" in text
    assert "node-version: 22" in text
    if workflow == "deploy-website.yml":
        assert "if: github.ref == 'refs/heads/main'" in text
        assert "- run: npx wrangler deploy" in text

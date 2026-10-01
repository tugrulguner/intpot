"""Guard consistent family presentation in the README."""

import re
from pathlib import Path


def test_readme_family_presentation():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    hero = re.search(r"<img\b[^>]+>", readme)
    assert hero is not None
    assert 'width="600"' in hero.group()
    assert 'Part of <a href="https://modepot.io/">ModePot</a>.' in readme[:1000]

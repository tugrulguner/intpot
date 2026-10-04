"""Guard consistent family presentation in the README."""

import re
from pathlib import Path


def test_readme_family_presentation():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    hero = re.search(r"<img\b[^>]+>", readme)
    assert hero is not None
    assert 'src="intpot_image.webp"' in hero.group()
    assert 'width="600"' in hero.group()
    after_hero = readme[readme.index("</p>", hero.end()) + 4 :]
    resource_row = re.search(r'<p align="center">(.*?)</p>', after_hero, re.DOTALL)
    assert resource_row is not None
    row = resource_row.group(1)
    assert 'Part of <a href="https://modepot.io/">ModePot</a>.' in row
    assert '<a href="https://intpot.modepot.io/">Project website</a>' in row
    assert '<a href="https://tugrul.modepot.io/">Created by Tugrul Guner</a>' in row


def test_readme_promotes_the_live_quickstart_playground_and_deep_docs():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    intro = readme.split("## Why intpot?", 1)[0]
    assert "One typed definition. Three interfaces." in intro
    assert 'href="https://intpot.modepot.io/quickstart/">Quick start<' in intro
    assert 'href="https://intpot.modepot.io/playground/">Playground<' in intro
    assert 'href="https://intpot.modepot.io/schema-reference/">Deep docs<' in intro
    assert 'href="#quick-start"' in intro

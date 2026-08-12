"""The skills shipped by `intpot add skills` must describe the current API.

These files land in other people's projects and are read by their coding agents,
so a stale one actively teaches the wrong thing. They sat at the v0.3.0 API for
five months without anything noticing.
"""

from __future__ import annotations

import dataclasses
import re

from intpot.core.models import ParameterInfo, ToolInfo
from intpot.skills.content import cli_skill_body, python_skill_body


def _all_skill_text() -> str:
    return cli_skill_body() + "\n" + python_skill_body()


def test_skills_cover_the_runtime_api():
    """The App runtime is the headline feature — it must not be missing again."""
    text = _all_skill_text()

    for symbol in ("intpot.App", "@app.tool", "app.serve", "eject"):
        assert symbol in text, f"skills never mention {symbol}"


def test_skills_cover_the_conversion_api():
    text = _all_skill_text()

    for symbol in ("intpot.load", "to_cli", "to_mcp", "to_api", "intpot to cli"):
        assert symbol in text, f"skills never mention {symbol}"


def test_skills_cover_every_cli_command():
    text = _all_skill_text()

    for command in ("intpot init", "intpot inspect", "intpot serve", "intpot eject"):
        assert command in text, f"skills never mention `{command}`"


def test_skills_only_reference_real_parameter_fields():
    """Catches the reverse failure: documenting an attribute that never existed.

    The old skill printed `param.annotation`, which is spelled
    `type_annotation` — anyone following it got an AttributeError.
    """
    valid = {f.name for f in dataclasses.fields(ParameterInfo)} | {"required"}

    referenced = set(re.findall(r"\bparam\.(\w+)", _all_skill_text()))

    assert referenced, "expected the skills to show ParameterInfo usage"
    assert referenced <= valid, f"not real ParameterInfo fields: {referenced - valid}"


def test_skills_only_reference_real_tool_fields():
    valid = {f.name for f in dataclasses.fields(ToolInfo)}

    referenced = set(re.findall(r"\btool\.(\w+)", _all_skill_text()))

    assert referenced, "expected the skills to show ToolInfo usage"
    assert referenced <= valid, f"not real ToolInfo fields: {referenced - valid}"


def test_skills_do_not_promise_the_old_network_default():
    """serve --api binds loopback since 0.5.0."""
    text = _all_skill_text()

    assert "127.0.0.1" in text
    # 0.0.0.0 may only appear as the documented opt-in, never as the default.
    for line in text.splitlines():
        if "0.0.0.0" in line:
            assert re.search(r"opt|expose|network|host=", line), (
                f"0.0.0.0 mentioned without framing it as opt-in: {line!r}"
            )

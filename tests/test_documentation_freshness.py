from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text().lower()


def test_published_versions_have_no_stale_until_publication_claims():
    paths = [
        "README.md",
        "ROADMAP.md",
        "website/src/content/docs/conversion-boundaries.md",
        "src/intpot/templates/skills/intpot-cli.md",
        "src/intpot/templates/skills/intpot-python.md",
    ]
    for path in paths:
        body = text(path)
        assert "until publication" not in body, path
        assert "until v0.16.0 is available" not in body, path
        assert "until v0.14.0 is published" not in body, path
        assert "until v0.16.0 is published" not in body, path
        assert "v0.16.0 release candidate" not in body, path


def test_manual_guides_cover_informational_policy_and_cli_exposure():
    paths = [
        "website/src/content/docs/conversion-boundaries.md",
        "website/src/content/docs/schema-reference.md",
    ]
    for path in paths:
        body = text(path)
        for token in (
            "exclusive-informational",
            "callback_policy",
            ".assess(",
            ".project(",
            ".to_api(",
            ".to_mcp(",
            ".write(",
            "--callback-policy",
            "argument callbacks",
            "__annotate__",
        ):
            assert token.lower() in body, f"{path} missing {token}"


def test_shipped_skills_qualify_repeatable_enum_support():
    for path in (
        "src/intpot/templates/skills/intpot-cli.md",
        "src/intpot/templates/skills/intpot-python.md",
    ):
        body = text(path)
        assert "repeatable" in body and "string-enum" in body, path
        assert "all repeatable" not in body, path
        assert "repeatable" in body and ("unsupported" in body or "refuse" in body), (
            path
        )


def test_capability_and_build_guides_expose_runnable_main_only_examples():
    for path in (
        "website/src/content/docs/capabilities/index.mdx",
        "website/src/content/docs/build-an-app.md",
    ):
        body = text(path)
        for term in (
            "convert_enum_export.py",
            "convert_selected_tools.py",
            "convert_informational.py",
            "unreleased",
            "v0.16.0",
        ):
            assert term in body, (path, term)
    assert "app.eject(mode=" not in text(
        "website/src/content/docs/capabilities/index.mdx"
    )


def test_architecture_explains_the_conditional_worker_boundary():
    body = text("website/src/content/docs/architecture-internals.md")
    for term in (
        "callback_policy",
        "exclusive-informational",
        "__annotate__",
        "not a sandbox",
        "unreleased",
    ):
        assert term in body


def test_example_commands_include_scalar_slug_body_and_a_real_mcp_client():
    body = (ROOT / "examples/README.md").read_text()
    assert "-d '\"Hello World\"'" in body
    for example in ("enum", "selected", "informational"):
        assert f"call_converted_mcp.py {example} " in body
    assert "PYTHONPATH=examples uv run --no-sync uvicorn informational_api:app" in body

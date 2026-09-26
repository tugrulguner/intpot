from __future__ import annotations

from types import ModuleType
from typing import Annotated, Any

import typer
from click import unstyle
from fastapi import FastAPI, Header, Query
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.inspectors.api import APIInspector
from intpot.core.inspectors.cli import CLIInspector
from intpot.core.models import (
    ApplicationSchema,
    ParameterInfo,
    ParameterSchema,
    ParamSource,
    SourceType,
)
from intpot.runtime import RegisteredTool
from intpot.runtime_builders import build_fastapi_app, build_typer_app

runner = CliRunner()


def test_parameter_alias_metadata_round_trips_without_shifting_positional_fields() -> (
    None
):
    mutable = ParameterInfo(
        "account_id",
        "str",
        "default-account",
        "Account identifier",
        None,
        None,
        "source_account_id",
        "customer-id",
        ["--customer-id", "-c"],
    )
    immutable = ParameterSchema.from_info(mutable)

    assert immutable == ParameterSchema(
        "account_id",
        "str",
        "default-account",
        "Account identifier",
        None,
        None,
        "source_account_id",
        "customer-id",
        ("--customer-id", "-c"),
    )
    assert immutable.to_info() == mutable
    assert immutable.to_dict()["interface_name"] == "customer-id"
    assert immutable.to_dict()["aliases"] == ["--customer-id", "-c"]


def test_fastapi_aliases_survive_inspection_live_serving_and_generation() -> None:
    source = FastAPI()

    @source.get("/customers")
    def lookup_customer(
        account_id: Annotated[str, Query(alias="customer-id")],
        trace_id: Annotated[str | None, Header(alias="X-Trace-ID")] = None,
    ) -> dict[str, str | None]:
        return {"account_id": account_id, "trace_id": trace_id}

    [info] = APIInspector().inspect(source)
    account, trace = info.parameters
    assert account.name == "account_id"
    assert account.interface_name == "customer-id"
    assert account.aliases == []
    assert account.param_source is ParamSource.query
    assert trace.name == "trace_id"
    assert trace.interface_name == "X-Trace-ID"
    assert trace.param_source is ParamSource.header

    schema = ApplicationSchema.from_tools(
        name="aliases", source_type=SourceType.API, tools=(info,)
    )
    frozen_account, frozen_trace = schema.tools[0].parameters
    assert frozen_account.interface_name == "customer-id"
    assert frozen_trace.interface_name == "X-Trace-ID"
    assert frozen_account.to_dict()["interface_name"] == "customer-id"

    live: Any = build_fastapi_app(
        "aliases", [RegisteredTool(func=lookup_customer, info=info)]
    )
    generated = ModuleType("generated_fastapi_aliases")
    exec(
        compile(APIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (source, live, generated.app):
        operation = app.openapi()["paths"]["/customers"]["get"]
        parameters = {
            (parameter["in"], parameter["name"])
            for parameter in operation["parameters"]
        }
        assert parameters == {("query", "customer-id"), ("header", "X-Trace-ID")}
        response = TestClient(app).get(
            "/customers?customer-id=acct-1", headers={"X-Trace-ID": "trace-1"}
        )
        assert response.status_code == 200
        assert response.json() == {"account_id": "acct-1", "trace_id": "trace-1"}

        rejected = TestClient(app).get(
            "/customers?account_id=acct-1", headers={"trace_id": "trace-1"}
        )
        assert rejected.status_code == 422


def test_typer_option_aliases_survive_inspection_live_serving_and_generation() -> None:
    source = typer.Typer()

    @source.command()
    def lookup_customer(
        account_id: Annotated[str, typer.Option("--customer-id", "-c")],
    ) -> None:
        print(account_id)

    [info] = CLIInspector().inspect(source)
    [account] = info.parameters
    assert account.name == "account_id"
    assert account.interface_name == "customer-id"
    assert account.aliases == ["--customer-id", "-c"]

    schema = ApplicationSchema.from_tools(
        name="aliases", source_type=SourceType.CLI, tools=(info,)
    )
    frozen = schema.tools[0].parameters[0]
    assert frozen.interface_name == "customer-id"
    assert frozen.aliases == ("--customer-id", "-c")

    live = build_typer_app("aliases", [RegisteredTool(func=lookup_customer, info=info)])
    generated = ModuleType("generated_cli_aliases")
    exec(
        compile(CLIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (source, live, generated.app):
        for alias in ("--customer-id", "-c"):
            result = runner.invoke(app, [alias, "acct-1"])
            assert result.exit_code == 0, result.output
            assert result.output.strip() == "acct-1"

        rejected = runner.invoke(app, ["--account-id", "acct-1"])
        assert rejected.exit_code != 0


def test_typer_option_aliases_survive_registered_command_fallback(
    monkeypatch: Any,
) -> None:
    source = typer.Typer()

    @source.command()
    def lookup_customer(
        account_id: Annotated[str, typer.Option("--customer-id", "-c")],
    ) -> None:
        print(account_id)

    def fail_to_build_click_tree(app: Any) -> Any:
        del app
        raise RuntimeError("unsupported Typer/Click combination")

    monkeypatch.setattr(typer.main, "get_group", fail_to_build_click_tree)

    [info] = CLIInspector().inspect(source)
    [account] = info.parameters
    assert account.interface_name == "customer-id"
    assert account.aliases == ["--customer-id", "-c"]
    assert account.required is True


def test_typer_boolean_option_pair_survives_live_and_generated_cli() -> None:
    source = typer.Typer()

    @source.command()
    def report(
        verbose: Annotated[bool, typer.Option("--verbose/--no-verbose", "-v")] = True,
    ) -> None:
        print(verbose)

    [info] = CLIInspector().inspect(source)
    [verbose] = info.parameters
    assert verbose.interface_name == "verbose"
    assert verbose.aliases == ["--verbose/--no-verbose", "-v"]

    schema = ApplicationSchema.from_tools(
        name="aliases", source_type=SourceType.CLI, tools=(info,)
    )
    live = build_typer_app("aliases", [RegisteredTool(func=report, info=info)])
    generated = ModuleType("generated_boolean_option_aliases")
    exec(
        compile(CLIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (source, live, generated.app):
        enabled = runner.invoke(app, ["--verbose"])
        assert enabled.exit_code == 0, enabled.output
        assert enabled.output.strip() == "True"
        disabled = runner.invoke(app, ["--no-verbose"])
        assert disabled.exit_code == 0, disabled.output
        assert disabled.output.strip() == "False"


def test_fastapi_aliases_become_required_and_optional_cli_options() -> None:
    source = FastAPI()

    @source.get("/customers")
    def lookup_customer(
        account_id: Annotated[str, Query(alias="customer-id")],
        trace_id: Annotated[str | None, Header(alias="X-Trace-ID")] = None,
    ) -> str:
        return f"{account_id}:{trace_id}"

    [info] = APIInspector().inspect(source)
    schema = ApplicationSchema.from_tools(
        name="aliases", source_type=SourceType.API, tools=(info,)
    )
    live = build_typer_app("aliases", [RegisteredTool(func=lookup_customer, info=info)])
    generated = ModuleType("generated_api_aliases_to_cli")
    exec(
        compile(CLIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (live, generated.app):
        result = runner.invoke(
            app,
            ["--customer-id", "acct-1", "--X-Trace-ID", "trace-1"],
        )
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "acct-1:trace-1"

        missing = runner.invoke(app, [])
        assert missing.exit_code != 0
        assert "--customer-id" in unstyle(missing.output)

        rejected = runner.invoke(app, ["acct-1"])
        assert rejected.exit_code != 0


def test_typer_option_names_become_fastapi_body_aliases() -> None:
    source = typer.Typer()

    @source.command()
    def lookup_customer(
        account_id: Annotated[str, typer.Option("--customer-id", "-c")],
        region: Annotated[str, typer.Option("--region-code", "-r")],
    ) -> str:
        return f"{account_id}:{region}"

    [info] = CLIInspector().inspect(source)
    schema = ApplicationSchema.from_tools(
        name="aliases", source_type=SourceType.CLI, tools=(info,)
    )
    live: Any = build_fastapi_app(
        "aliases", [RegisteredTool(func=lookup_customer, info=info)]
    )
    generated = ModuleType("generated_cli_aliases_to_api")
    exec(
        compile(APIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (live, generated.app):
        route = next(route for route in app.routes if route.path == "/lookup-customer")
        assert {field.alias for field in route.dependant.body_params} == {
            "customer-id",
            "region-code",
        }

        response = TestClient(app).post(
            "/lookup-customer",
            json={"customer-id": "acct-1", "region-code": "us"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == "acct-1:us"

        rejected = TestClient(app).post(
            "/lookup-customer",
            json={"account_id": "acct-1", "region": "us"},
        )
        assert rejected.status_code == 422

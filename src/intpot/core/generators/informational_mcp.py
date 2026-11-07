"""Explicit informational adaptation over framework-owned generated MCP tools."""

from __future__ import annotations

import ast
from dataclasses import replace

from intpot.core.generators.informational_api import _WORKER, _occupied
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.informational_policy import qualify_informational_callback
from intpot.core.models import ApplicationSchema


def generate_informational_mcp(schema: ApplicationSchema) -> str:
    """Preserve ordinary wrappers; register conditional tools using public APIs."""
    tree = ast.parse(MCPGenerator().generate(replace(schema, callback_policy=None)))
    occupied = _occupied(tree)

    def allocate(stem: str) -> str:
        name = "_intpot_info_" + stem
        while name in occupied:
            name += "_"
        occupied.add(name)
        return name

    modules = {
        module: allocate(module)
        for module in (
            "builtins",
            "typing",
            "pydantic",
            "asyncio",
            "subprocess",
            "sys",
            "json",
        )
    }
    b, t, p, a, sp, sy, j = modules.values()
    tool_type, result_type = allocate("Tool"), allocate("ToolResult")
    protocol = allocate("protocol")
    registry = allocate("legacy_tools")
    legacy = allocate("legacy_server")
    structured = allocate("structured_protocol")
    imports = ast.parse(
        "\n".join(f"import {module} as {alias}" for module, alias in modules.items())
        + f"""
from fastmcp.tools import Tool as {tool_type}
try:
    from fastmcp.tools import ToolResult as {result_type}
except ImportError:
    try:
        from fastmcp.tools.tool import ToolResult as {result_type}
    except ImportError:
        {result_type} = None
from mcp import types as {protocol}
"""
    ).body
    position = (
        1
        if tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
        else 0
    )
    while (
        position < len(tree.body)
        and isinstance(tree.body[position], ast.ImportFrom)
        and tree.body[position].module == "__future__"
    ):
        position += 1
    tree.body[position:position] = imports
    creations = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "mcp"
            for target in node.targets
        )
        and isinstance(node.value, ast.Call)
    ]
    if len(creations) != 1 or not isinstance(creations[0].value.func, ast.Name):
        raise TypeError("Unsupported generated MCP server constructor")
    creation = creations[0]
    original_class = creation.value.func.id
    legacy_code = f"""
{registry} = {{}}
{structured} = "outputSchema" in {protocol}.Tool.model_fields and "structuredContent" in {protocol}.CallToolResult.model_fields
class {legacy}({original_class}):
    async def list_tools(self):
        ordinary = await super().list_tools()
        return [tool for tool in ordinary if tool.name not in {registry}] + [entry[0] for entry in {registry}.values()]
    async def call_tool(self, name, arguments):
        entry = {registry}.get(name)
        if entry is None:
            return await super().call_tool(name, arguments)
        text = await entry[1](arguments)
        if {b}.type(text) is not {b}.str:
            raise {b}.TypeError("CLI-to-MCP result must be text")
        content = [{protocol}.TextContent(type="text", text=text)]
        return (content, {{"result": text}}) if {structured} else content
"""
    constructor = ast.parse(
        f"({legacy} if {result_type} is None else {original_class})", mode="eval"
    ).body
    creation.value.func = constructor
    tree.body[tree.body.index(creation) : tree.body.index(creation)] = ast.parse(
        legacy_code
    ).body
    invoke, worker = allocate("invoke"), allocate("worker")
    chunks = [
        f"""
{worker} = {_WORKER!r}
def {invoke}(packet):
    try:
        response = {sp}.run([{sy}.executable, "-c", {worker}], input={j}.dumps(packet), capture_output=True, text=True, timeout=30)
    except {sp}.TimeoutExpired as error:
        raise {b}.RuntimeError("Informational callback timed out") from error
    if response.returncode != 0:
        raise {b}.RuntimeError("Informational callback worker failed")
    answer = {j}.loads(response.stdout)
    if answer.get("ok") is not True:
        raise {b}.RuntimeError(answer.get("error_type", "CallbackError") + ": " + answer.get("error", "Informational callback failed"))
    return answer["text"]
"""
    ]
    for tool in schema.tools:
        callbacks = [
            parameter
            for parameter in tool.parameters
            if parameter.informational_callback is not None
        ]
        if not callbacks:
            continue
        matches = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == tool.name
            and node.decorator_list
        ]
        if len(matches) != 1 or isinstance(matches[0], ast.AsyncFunctionDef):
            raise TypeError("Unsupported generated informational MCP tool")
        endpoint = matches[0]
        if not isinstance(endpoint.returns, ast.Name) or endpoint.returns.id != "str":
            raise TypeError(
                "Informational MCP requires the existing text result contract"
            )
        original = endpoint.name
        regular = allocate("regular_" + original)
        endpoint.name, endpoint.decorator_list = regular, []
        fields = endpoint.args.args
        defaults = [ast.Constant(value=Ellipsis)] * (
            len(fields) - len(endpoint.args.defaults)
        ) + endpoint.args.defaults
        if len(fields) != len(tool.parameters):
            raise TypeError("Unsupported generated MCP parameter layout")
        base, normal = allocate("base_" + original), allocate("normal_" + original)
        rules = {parameter.name: parameter.default is None for parameter in callbacks}
        chunks.append(f"""
class {base}({p}.BaseModel):
    class Config:
        extra = "forbid"
    @{p}.root_validator(pre=True, allow_reuse=True)
    def strict_flags(cls, values):
        if {b}.isinstance(values, {b}.dict):
            for key, nullable in {rules!r}.items():
                if key in values:
                    value = values[key]
                    if {b}.type(value) is not {b}.bool and not (nullable and value is None):
                        raise {b}.ValueError("Informational flags require literal booleans")
        return values
""")
        normal_fields, internals, packets = [], [], {}
        for index, (parameter, field, default) in enumerate(
            zip(tool.parameters, fields, defaults, strict=True)
        ):
            internal = "field_" + str(index)
            internals.append(internal)
            annotation = (
                ast.unparse(field.annotation) if field.annotation else f"{b}.str"
            )
            keywords = ""
            if isinstance(default, ast.Call):
                # Only framework-owned Field calls encode wrapper defaults/bounds.
                value = (
                    default.args[0] if default.args else ast.Constant(value=Ellipsis)
                )
                keywords = "".join(
                    f", {keyword.arg}={ast.unparse(keyword.value)}"
                    for keyword in default.keywords
                    if keyword.arg in ("ge", "le", "description")
                )
            else:
                value = default
            if parameter in callbacks:
                annotation = (
                    f"{t}.Literal[False, None]"
                    if parameter.default is None
                    else f"{t}.Literal[False]"
                )
                spec = parameter.informational_callback
                assert spec is not None
                packets[internal] = {
                    "module": spec.module,
                    "export": spec.export,
                    "digest": qualify_informational_callback(spec),
                }
            normal_fields.append(
                f"{internal!r}: ({annotation}, {p}.Field({ast.unparse(value)}, alias={parameter.name!r}{keywords}))"
            )
        chunks.append(
            f"{normal} = {p}.create_model({normal!r}, __base__={base}, **{{"
            + ", ".join(normal_fields)
            + "})"
        )
        models = [normal]
        for active in callbacks:
            branch, branch_fields = (
                allocate("branch_" + original + "_" + active.name),
                [],
            )
            for index, parameter in enumerate(tool.parameters):
                if parameter is active:
                    annotation, default = f"{t}.Literal[True]", "..."
                elif parameter in callbacks:
                    annotation = (
                        f"{t}.Literal[False, None]"
                        if parameter.default is None
                        else f"{t}.Literal[False]"
                    )
                    default = "None" if parameter.default is None else "False"
                else:
                    if parameter.string_enum is not None:
                        annotation = (
                            f"{b}.list[{b}.str]"
                            if parameter.string_enum.many
                            else f"{b}.str"
                        )
                    elif parameter.type_annotation in ("str", "int", "float", "bool"):
                        annotation = (
                            f"{t}.Union[{b}.{parameter.type_annotation}, {b}.str]"
                        )
                    else:
                        raise TypeError(
                            f"Unsupported informational wire shape for {parameter.name}"
                        )
                    default = "None"
                branch_fields.append(
                    f"{internals[index]!r}: ({annotation}, {p}.Field({default}, alias={parameter.name!r}))"
                )
            chunks.append(
                f"{branch} = {p}.create_model({branch!r}, __base__={base}, **{{"
                + ", ".join(branch_fields)
                + "})"
            )
            models.append(branch)
        adapter, packet_name, custom_tool = (
            allocate("adapter_" + original),
            allocate("packets_" + original),
            allocate("tool_" + original),
        )
        arguments = ", ".join(
            f"{parameter.name}="
            + (
                "None"
                if parameter in callbacks
                else f"{b}.getattr(request, {internal!r})"
            )
            for parameter, internal in zip(tool.parameters, internals, strict=True)
        )
        dispatch = allocate("dispatch_" + original)
        input_schema = allocate("input_" + original)
        output_schema = allocate("output_" + original)
        chunks.append(f"""
{adapter} = {p}.TypeAdapter({t}.Union[{", ".join(models)}])
{packet_name} = {packets!r}
{input_schema} = {{**{adapter}.json_schema(by_alias=True), "type": "object"}}
{output_schema} = {{"type":"object", "properties":{{"result":{{"type":"string"}}}}, "required":["result"], "x-fastmcp-wrap-result":True}}
async def {dispatch}(arguments):
    request = {adapter}.validate_python(arguments)
    for field, packet in {packet_name}.items():
        if {b}.getattr(request, field) is True:
            return await {a}.to_thread({invoke}, packet)
    return await {a}.to_thread({regular}, {arguments})
class {custom_tool}({tool_type}):
    async def run(self, arguments):
        text = await {dispatch}(arguments)
        return {result_type}(content=text, structured_content={{"result": text}})
if {result_type} is None:
    {registry}[{tool.interface_name!r}] = ({protocol}.Tool(name={tool.interface_name!r}, description={tool.description!r}, inputSchema={input_schema}, **({{"outputSchema": {output_schema}}} if {structured} else {{}})), {dispatch})
else:
    mcp.add_tool({custom_tool}(name={tool.interface_name!r}, description={tool.description!r}, parameters={input_schema}, output_schema={output_schema}))
""")
    insert = next(
        (
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.If)
            and ast.unparse(node.test).startswith("__name__ ==")
        ),
        len(tree.body),
    )
    tree.body[insert:insert] = ast.parse("\n".join(chunks)).body
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"

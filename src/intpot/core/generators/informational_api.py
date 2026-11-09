"""Explicit informational adaptation over framework-owned generated API wrappers."""

from __future__ import annotations

import ast
import copy
from dataclasses import replace

from intpot.core.generators.api import APIGenerator
from intpot.core.informational_policy import qualify_informational_callback
from intpot.core.models import ApplicationSchema

# This runs in a request-owned child, not the shared HTTP process. No intpot import.
_WORKER = """import contextlib, hashlib, importlib, io, json, pathlib, sys, tokenize, types
packet=json.loads(sys.stdin.read())
out,err=io.StringIO(),io.StringIO()
answer={}
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    try:
        import typer
        exit_class=vars(typer)["Exit"]
        module=importlib.import_module(packet["module"])
        function=vars(module).get(packet["export"])
        if type(function) is not types.FunctionType or function.__globals__ is not vars(module):
            raise TypeError("Callback export is unverified")
        with tokenize.open(pathlib.Path(function.__code__.co_filename)) as stream:
            source=stream.read()
        if hashlib.sha256(source.encode("utf-8")).hexdigest()!=packet["digest"]:
            raise TypeError("Callback source changed")
        compiled=compile(source,function.__code__.co_filename,"exec",dont_inherit=True,optimize=sys.flags.optimize)
        def matches(code):
            return sum((constant==function.__code__)+matches(constant) for constant in code.co_consts if type(constant) is types.CodeType)
        if matches(compiled)!=1:
            raise TypeError("Callback code does not match source")
        try:
            function(True)
        except exit_class as error:
            if type(error.exit_code) is not int or error.exit_code!=0:
                raise RuntimeError("Callback exited unsuccessfully") from error
            answer={"ok":True}
        except SystemExit as error:
            if error.code is not None and (type(error.code) is not int or error.code!=0):
                raise RuntimeError("Callback exited unsuccessfully") from error
            answer={"ok":True}
        else:
            raise RuntimeError("Informational callback returned without exit")
    except BaseException as error:
        answer={"ok":False,"error_type":type(error).__name__,"error":str(error)}
answer.update(text=out.getvalue(),stderr=err.getvalue())
print(json.dumps(answer))
"""


def _occupied(tree: ast.Module) -> set[str]:
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
    return names


def _default_field(default: ast.expr, pydantic: str, alias: str) -> str:
    """Retain defaults/bounds from the existing framework-owned API wrapper."""
    if not isinstance(default, ast.Call):
        raise TypeError("Unsupported generated API default")
    value = next((k.value for k in default.keywords if k.arg == "default"), None)
    if value is None:
        value = default.args[0] if default.args else ast.Constant(value=Ellipsis)
    keywords = [
        ast.keyword(arg=k.arg, value=copy.deepcopy(k.value))
        for k in default.keywords
        if k.arg in ("description", "ge", "le")
    ]
    keywords.append(ast.keyword(arg="alias", value=ast.Constant(value=alias)))
    call = ast.Call(
        func=ast.Attribute(
            value=ast.Name(id=pydantic, ctx=ast.Load()), attr="Field", ctx=ast.Load()
        ),
        args=[copy.deepcopy(value)],
        keywords=keywords,
    )
    return ast.unparse(ast.fix_missing_locations(call))


def generate_informational_api(schema: ApplicationSchema) -> str:
    """Render the explicit adaptation; callers must first preserve all other guards."""
    tree = ast.parse(APIGenerator().generate(replace(schema, callback_policy=None)))
    occupied = _occupied(tree)

    def allocate(stem: str) -> str:
        name = "_intpot_info_" + stem
        while name in occupied:
            name += "_"
        occupied.add(name)
        return name

    aliases = {
        key: allocate(key)
        for key in (
            "builtins",
            "typing",
            "pydantic",
            "fastapi",
            "subprocess",
            "sys",
            "json",
        )
    }
    b, t, p, f, sp, sy, j = (aliases[key] for key in aliases)
    imports = ast.parse(
        "\n".join(f"import {module} as {alias}" for module, alias in aliases.items())
    ).body
    # Preserve future imports after the module docstring.
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
    invoke_name = allocate("invoke")
    worker_name = allocate("worker")
    prelude = f"""
{worker_name} = {_WORKER!r}
def {invoke_name}(packet):
    try:
        response = {sp}.run([{sy}.executable, "-c", {worker_name}], input={j}.dumps(packet), capture_output=True, text=True, timeout=30)
    except {sp}.TimeoutExpired as error:
        raise {f}.HTTPException(status_code=504, detail="Informational callback timed out") from error
    if response.returncode != 0:
        raise {f}.HTTPException(status_code=500, detail="Informational callback worker failed")
    try:
        answer = {j}.loads(response.stdout)
    except ({b}.ValueError, {b}.TypeError) as error:
        raise {f}.HTTPException(status_code=500, detail="Invalid callback worker response") from error
    if answer.get("ok") is not True:
        raise {f}.HTTPException(status_code=500, detail=answer.get("error_type", "CallbackError") + ": " + answer.get("error", "Informational callback failed"))
    return {{"result": answer["text"]}}
"""
    prelude_nodes = ast.parse(prelude).body
    additions: list[ast.stmt] = []
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
            raise TypeError("Unsupported generated informational route")
        endpoint = matches[0]
        if not isinstance(endpoint.returns, ast.Name) or endpoint.returns.id != "dict":
            raise TypeError(
                "Informational API requires the existing object result contract"
            )
        original_name = endpoint.name
        regular_name = allocate("regular_" + original_name)
        decorators = copy.deepcopy(endpoint.decorator_list)
        endpoint.name = regular_name
        endpoint.decorator_list = []
        fields = endpoint.args.args
        defaults = endpoint.args.defaults
        if len(fields) != len(tool.parameters) or len(defaults) != len(fields):
            raise TypeError("Unsupported generated parameter layout")
        base = allocate("base_" + original_name)
        normal = allocate("normal_" + original_name)
        flag_rules = {
            parameter.interface_name or parameter.name: parameter.default is None
            for parameter in callbacks
        }
        chunks = [
            f"""
class {base}({p}.BaseModel):
    class Config:
        extra = "forbid"
    @{p}.root_validator(pre=True, allow_reuse=True)
    def strict_flags(cls, values):
        if {b}.isinstance(values, {b}.dict):
            for key, nullable in {flag_rules!r}.items():
                if key in values:
                    value = values[key]
                    if {b}.type(value) is not {b}.bool and not (nullable and value is None):
                        raise {b}.ValueError("Informational flags require literal booleans")
        return values
"""
        ]
        ordinary_fields = []
        internals = []
        packets = {}
        for index, (parameter, field, default) in enumerate(
            zip(tool.parameters, fields, defaults, strict=True)
        ):
            internal = "field_" + str(index)
            internals.append(internal)
            wire = parameter.interface_name or parameter.name
            annotation = (
                ast.unparse(field.annotation) if field.annotation is not None else "str"
            )
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
            ordinary_fields.append(
                f"{internal!r}: ({annotation}, {_default_field(default, p, wire)})"
            )
        chunks.append(
            f"{normal} = {p}.create_model({normal!r}, __base__={base}, **{{"
            + ", ".join(ordinary_fields)
            + "})"
        )
        models = [normal]
        for active in callbacks:
            info_name = allocate("branch_" + original_name + "_" + active.name)
            info_fields = []
            for index, (parameter, _field) in enumerate(
                zip(tool.parameters, fields, strict=True)
            ):
                internal = internals[index]
                wire = parameter.interface_name or parameter.name
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
                info_fields.append(
                    f"{internal!r}: ({annotation}, {p}.Field({default}, alias={wire!r}))"
                )
            chunks.append(
                f"{info_name} = {p}.create_model({info_name!r}, __base__={base}, **{{"
                + ", ".join(info_fields)
                + "})"
            )
            models.append(info_name)
        request_name = allocate("request_" + original_name)
        packet_name = allocate("packets_" + original_name)
        chunks.append(f"{packet_name} = {packets!r}")
        arguments = ", ".join(
            f"{parameter.name}="
            + (
                "None"
                if parameter in callbacks
                else f"{b}.getattr({request_name}, {internal!r})"
            )
            for parameter, internal in zip(tool.parameters, internals, strict=True)
        )
        wrapper = f"""
def {original_name}({request_name}: {t}.Union[{", ".join(models)}]) -> {b}.dict:
    for field, packet in {packet_name}.items():
        if {b}.getattr({request_name}, field) is True:
            return {invoke_name}(packet)
    return {regular_name}({arguments})
"""
        nodes = ast.parse("\n".join(chunks) + wrapper).body
        nodes[-1].decorator_list = decorators
        additions.extend(nodes)
    # Define adapters before the conventional __main__ launch block.
    insert = next(
        (
            i
            for i, node in enumerate(tree.body)
            if isinstance(node, ast.If)
            and ast.unparse(node.test).startswith("__name__ ==")
        ),
        len(tree.body),
    )
    tree.body[insert:insert] = prelude_nodes + additions
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"

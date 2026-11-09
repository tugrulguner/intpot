"""Generate a FastAPI app from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import (
    BaseGenerator,
    GenerationInput,
    generation_context,
)
from intpot.core.models import ApplicationSchema, SourceType


class APIGenerator(BaseGenerator):
    def generate(self, source: GenerationInput) -> str:
        if isinstance(source, ApplicationSchema) and source.callback_policy is not None:
            from intpot.core.generators.informational_api import (
                generate_informational_api,
            )
            from intpot.core.informational_projection import (
                qualify_informational_schema,
            )

            if source.target_type not in (None, SourceType.API):
                raise ValueError("Callback policy projection targets another interface")
            qualified = qualify_informational_schema(source, source.callback_policy)
            return generate_informational_api(qualified)
        schema = generation_context(
            source, default_name="FastAPI", target=SourceType.API
        )
        return render_template(
            "api_app.py.j2", tools=schema.tools, app_name=schema.name, schema=schema
        )

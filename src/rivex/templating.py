from __future__ import annotations

from typing import Any

from rivex.responses import HTMLResponse


class Jinja2Templates:
    def __init__(self, directory: str):
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            raise ImportError(
                "jinja2 must be installed to use Jinja2Templates. "
                "Install it with: pip install jinja2"
            ) from None
        self.env = Environment(
            loader=FileSystemLoader(directory),
            autoescape=True,
        )

    def TemplateResponse(
        self,
        name: str,
        context: dict[str, Any],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> HTMLResponse:
        template = self.env.get_template(name)
        content = template.render(**context)
        return HTMLResponse(content=content, status_code=status_code, headers=headers)

    def render(self, name: str, **context: Any) -> HTMLResponse:
        """Render a template and return an HTMLResponse (shorthand)."""
        return self.TemplateResponse(name, context)

    def get_template(self, name: str) -> Any:
        return self.env.get_template(name)

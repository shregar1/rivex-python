from __future__ import annotations

from typing import Any

from rivex.http.responses import HTMLResponse


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
        """Render ``name`` with ``context`` and wrap it in an :class:`HTMLResponse`.

        The Jinja2 environment was created with ``autoescape=True``,
        so caller-supplied values are HTML-escaped automatically unless
        explicitly marked safe (``Markup``). Status code and any extra
        headers (e.g. ``Cache-Control``) are forwarded onto the
        returned response so handlers can adjust them per render.

        Args:
            name: Template file name relative to the directory passed
                to the constructor.
            context: Template variables. Each key becomes a binding
                inside the template's global scope at render time.
            status_code: HTTP status for the response. Defaults to
                ``200``.
            headers: Optional response headers to attach to the
                rendered HTML.

        Returns:
            An :class:`HTMLResponse` carrying the rendered template
            body and the supplied metadata.
        """
        template = self.env.get_template(name)
        content = template.render(**context)
        return HTMLResponse(content=content, status_code=status_code, headers=headers)

    def render(self, name: str, **context: Any) -> HTMLResponse:
        """Render a template and return an HTMLResponse (shorthand)."""
        return self.TemplateResponse(name, context)

    def get_template(self, name: str) -> Any:
        """Return the underlying Jinja2 ``Template`` for ``name`` without rendering it.

        Exposed for callers that need to render the same template many
        times with distinct contexts and want to avoid the lookup
        overhead on each iteration. The returned object is whatever the
        Jinja2 ``Environment.get_template`` method returns — typically
        a :class:`jinja2.Template` instance.

        Args:
            name: Template file name relative to the directory passed
                to the constructor.

        Returns:
            The compiled Jinja2 template, ready for ``.render(**ctx)``.
        """
        return self.env.get_template(name)

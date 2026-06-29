import os
from html import escape as _html_escape


def render_react_docs(
    openapi_url: str,
    title: str = "API",
    description: str | None = None,
    favicon_url: str | None = None,
    logo_url: str | None = None,
) -> str:
    """Render the React docs shell with the OpenAPI URL injected.

    The prebuilt ``static/react_docs/index.html`` is a self-contained
    React app that fetches the spec on load and renders it.  We
    inject the spec URL plus the title (so the page title and the
    document <h1> reflect the user-supplied app name) right before
    ``</head>``.
    """
    path = os.path.join(os.path.dirname(__file__), "static", "react_docs", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return "<h1>RiveX React Docs not found. Please build the react app.</h1>"

    safe_title = _html_escape(title or "API")
    inject = (
        f"<title>{safe_title}</title>"
        f'<meta name="description" content="{_html_escape(description) if description else safe_title}"/>'
        f'<script>window.__RIVEX_TITLE__ = "{_html_escape(title or "API")}";'
        f'window.__RIVEX_SPEC_URL__ = "{_html_escape(openapi_url, quote=True)}";</script>'
    )
    if favicon_url:
        inject = f'<link rel="icon" href="{_html_escape(favicon_url)}"/>' + inject
    if logo_url:
        inject += f'<script>window.__RIVEX_LOGO_URL__ = "{_html_escape(logo_url)}";</script>'
    return html.replace("</head>", inject + "</head>")

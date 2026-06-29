from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class GraphQLMiddleware:
    """Serves a GraphQL endpoint at ``/graphql``.

    Integrates with Strawberry library for schema definition.

    Usage::

        import strawberry

        @strawberry.type
        class Query:
            @strawberry.field
            def hello(self) -> str:
                return "world"

        schema = strawberry.Schema(query=Query)
        app.add_middleware(GraphQLMiddleware, schema=schema, graphiql=True)
    """

    def __init__(
        self,
        schema: Any = None,
        graphiql: bool = True,
        endpoint: str = "/graphql",
        app: Any = None,
    ):
        self._schema = schema
        self._graphiql = graphiql
        self._endpoint = endpoint

    @property
    def schema(self) -> Any:
        return self._schema

    @schema.setter
    def schema(self, value: Any) -> None:
        self._schema = value

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        path = request_data.get("path", "/")
        if path != self._endpoint:
            return await call_next(request_data)

        method = request_data.get("method", "GET").upper()

        if method == "GET" and self._graphiql:
            return {
                "status": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": self._graphiql_html(),
            }

        if method == "POST":
            body = request_data.get("body", "{}")
            if isinstance(body, bytes):
                body = body.decode()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return {"status": 400, "body": json.dumps({"error": "Invalid JSON"})}

            query = payload.get("query", "")
            variables = payload.get("variables", {})
            operation_name = payload.get("operationName")

            if self._schema is None:
                return {"status": 500, "body": json.dumps({"error": "No schema configured"})}

            try:
                if hasattr(self._schema, "execute_sync"):
                    result = self._schema.execute_sync(query, variable_values=variables, operation_name=operation_name)
                elif hasattr(self._schema, "execute"):
                    import asyncio
                    if asyncio.iscoroutinefunction(self._schema.execute):
                        result = await self._schema.execute(query, variable_values=variables, operation_name=operation_name)
                    else:
                        result = self._schema.execute(query, variable_values=variables, operation_name=operation_name)
                else:
                    result = self._schema.execute_sync(query, variable_values=variables, operation_name=operation_name)

                response_data = {}
                if hasattr(result, "data") and result.data is not None:
                    response_data["data"] = result.data
                if hasattr(result, "errors") and result.errors:
                    response_data["errors"] = [
                        {"message": str(e)} for e in result.errors
                    ]
                return {"status": 200, "body": json.dumps(response_data)}
            except Exception as e:
                return {"status": 500, "body": json.dumps({"error": str(e)})}

        return await call_next(request_data)

    def _graphiql_html(self) -> str:
        return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>GraphiQL</title>
  <style>body { margin: 0; } #graphiql { height: 100vh; }</style>
  <link rel="stylesheet" href="https://unpkg.com/graphiql/graphiql.min.css" />
</head>
<body>
  <div id="graphiql">Loading...</div>
  <script src="https://unpkg.com/react/umd/react.production.min.js"></script>
  <script src="https://unpkg.com/react-dom/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/graphiql/graphiql.min.js"></script>
  <script>
    const fetcher = graphQLParams => fetch('/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(graphQLParams),
    }).then(res => res.json());
    ReactDOM.render(React.createElement(GraphiQL, { fetcher }), document.getElementById('graphiql'));
  </script>
</body>
</html>"""


def graphql_query(description: str = ""):
    """Decorator to mark a method as a GraphQL query resolver."""
    def decorator(func):
        func._graphql_type = "query"
        func._graphql_description = description
        return func
    return decorator


def graphql_mutation(description: str = ""):
    """Decorator to mark a method as a GraphQL mutation resolver."""
    def decorator(func):
        func._graphql_type = "mutation"
        func._graphql_description = description
        return func
    return decorator

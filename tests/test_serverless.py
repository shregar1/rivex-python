from __future__ import annotations

from rivex import Rivex
from rivex.serverless import AwsLambdaHandler, CloudflareHandler, VercelHandler, AzureFunctionHandler
from rivex.asgi import ASGIAdapter


def test_aws_lambda_handler_import():
    app = Rivex()
    handler = AwsLambdaHandler(app)
    assert handler.app is app


def test_aws_lambda_handler_v1_event():
    app = Rivex()

    @app.get("/hello")
    async def hello():
        return {"status": 200, "headers": [("content-type", "text/plain")], "body": b"world"}

    handler = AwsLambdaHandler(app)
    event = {
        "version": "1.0",
        "httpMethod": "GET",
        "path": "/hello",
        "headers": {"content-type": "application/json"},
        "body": "",
        "isBase64Encoded": False,
    }
    result = handler(event)
    assert result["statusCode"] == 200


def test_aws_lambda_handler_v2_event():
    app = Rivex()

    @app.post("/api/data")
    async def data():
        return {"status": 201, "headers": [("content-type", "application/json")], "body": b'{"ok":true}'}

    handler = AwsLambdaHandler(app)
    event = {
        "version": "2.0",
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/api/data",
        "headers": {"content-type": "application/json"},
        "body": "",
        "isBase64Encoded": False,
    }
    result = handler(event)
    assert result["statusCode"] == 201


def test_cloudflare_handler_import():
    app = Rivex()
    handler = CloudflareHandler(app)
    assert handler.app is app


def test_vercel_handler_import():
    app = Rivex()
    handler = VercelHandler(app)
    assert handler.app is app


def test_azure_function_handler_import():
    app = Rivex()
    handler = AzureFunctionHandler(app)
    assert handler.app is app


def test_serverless_adapter_asgi_scope():
    app = Rivex()
    handler = AwsLambdaHandler(app)
    scope = handler._asgi_scope("GET", "/test", [(b"host", b"example.com")], b"hello")
    assert scope["method"] == "GET"
    assert scope["path"] == "/test"
    assert scope["headers"] == [(b"host", b"example.com")]
    assert scope["query_string"] == b""


def test_aws_lambda_handler_errors_gracefully():
    app = Rivex()

    @app.get("/error")
    async def error():
        raise ValueError("test error")

    handler = AwsLambdaHandler(app)

    from rivex._compat import HAS_CORE
    event = {
        "version": "1.0",
        "httpMethod": "GET",
        "path": "/error",
        "headers": {},
        "body": "",
        "isBase64Encoded": False,
    }
    result = handler(event)
    # Should return 500 error
    assert result["statusCode"] == 500

"""``rivex.middleware.request_validation`` — pluggable rule-based validation middleware."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, Optional, Union


class IValidationRule(ABC):
    """Base class for request/response validation rules.

    Subclasses implement :meth:`validate_request` to short-circuit the
    pipeline (returning a response dict when a request is bad) and
    :meth:`sanitize_response` to rewrite the response body on the way
    back. Use :meth:`is_excluded` to skip rules for specific paths /
    methods (e.g. health endpoints).
    """

    @abstractmethod
    def is_excluded(self, path: str, method: str) -> bool:
        """Return ``True`` when the rule should be skipped for this request."""

    @abstractmethod
    async def validate_request(self, request_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Return a response dict to abort, or ``None`` to continue."""

    @abstractmethod
    async def sanitize_response(
        self,
        response: dict[str, Any],
        request_data: Optional[dict[str, Any]] = None,
    ) -> Optional[bytes]:
        """Return a replacement body, or ``None`` to leave it unchanged.

        ``request_data`` is forwarded by :class:`RequestValidationMiddleware`
        so rules can branch on path / route name / state. The legacy
        single-argument signature is still supported for back-compat
        — old rules just ignore the second parameter.
        """


class RequestValidationMiddleware:
    """Run every registered :class:`IValidationRule` against the request body.

    Each rule that returns a response from :meth:`validate_request` aborts
    the pipeline immediately. On the response side every rule gets a
    chance to :meth:`sanitize_response` and replace the body bytes.
    """

    def __init__(self, rules: Sequence[IValidationRule] | None = None) -> None:
        self._rules: list[IValidationRule] = list(rules or [])

    @classmethod
    def builder(cls) -> "RequestValidationMiddlewareBuilder":
        """Return a fluent builder for assembling a configured middleware.

        Returns:
            A fresh :class:`RequestValidationMiddlewareBuilder` with no
            rules attached, ready to be populated via ``with_rule`` /
            ``with_rules`` calls before :meth:`RequestValidationMiddlewareBuilder.build`.
        """
        return RequestValidationMiddlewareBuilder()

    def register(self, rule_or_rules: Union[IValidationRule, Sequence[IValidationRule]]) -> "RequestValidationMiddleware":
        """Register one rule or a sequence of rules on this middleware.

        Strings and bytes are explicitly excluded from the sequence branch
        because duck-typing would otherwise classify them as iterable rule
        lists. Newly registered rules run alongside any previously added
        ones.

        Args:
            rule_or_rules: Either a single :class:`IValidationRule`
                instance or any non-string/bytes sequence of such
                instances.

        Returns:
            This middleware instance, to allow chained configuration.
        """
        if isinstance(rule_or_rules, Sequence) and not isinstance(rule_or_rules, (str, bytes)):
            self._rules.extend(rule_or_rules)
        else:
            self._rules.append(rule_or_rules)
        return self

    def register_rule(self, rule: IValidationRule) -> "RequestValidationMiddleware":
        """Register a single :class:`IValidationRule`.

        Convenience wrapper around :meth:`register` for callers that
        always pass exactly one rule.

        Args:
            rule: The rule to add to this middleware's rule list.

        Returns:
            This middleware instance, to allow chained configuration.
        """
        return self.register(rule)

    async def process(self, request_data: dict[str, Any], call_next: Callable) -> dict[str, Any]:
        """Run every registered rule on the request and the response body.

        Iterates the configured rules in order, calling
        :meth:`IValidationRule.is_excluded` to filter out rules that do
        not apply to this path/method, then
        :meth:`IValidationRule.validate_request` to short-circuit the
        pipeline with an error response when a rule fires. After
        delegating to ``call_next`` to obtain the downstream response, a
        copy of ``request_data`` is stashed on the response dict so
        rules can branch on it during sanitization, and each non-excluded
        rule's :meth:`IValidationRule.sanitize_response` is invoked to
        replace ``body`` when a rule returns a replacement.

        Args:
            request_data: The in-flight request envelope. Only the
                ``path`` and ``method`` keys are read here; they are
                used to filter excluded rules.
            call_next: Awaitable that invokes the next middleware or
                handler and returns the downstream response dict.

        Returns:
            Either an abort response produced by a rule's
            ``validate_request``, or the downstream response with any
            rule-supplied body replacement applied.
        """
        path = request_data.get("path") or ""
        method = request_data.get("method") or "GET"

        for rule in self._rules:
            if rule.is_excluded(path, method):
                continue
            abort = await rule.validate_request(request_data)
            if abort is not None:
                return abort

        response = await call_next(request_data)
        # Stamp the request onto the response so rule ``sanitize_response``
        # implementations can branch on path / route_name / state.
        if isinstance(response, dict):
            response.setdefault("_request_data", dict(request_data))
        for rule in self._rules:
            if rule.is_excluded(path, method):
                continue
            new_body = await rule.sanitize_response(response, request_data)
            if new_body is not None:
                response["body"] = new_body

        return response

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "RequestValidationMiddleware"


class RequestValidationMiddlewareBuilder:
    """Builder so users can register rules before :meth:`build`."""

    def __init__(self) -> None:
        self._rules: list[IValidationRule] = []

    def with_rule(self, rule: IValidationRule) -> "RequestValidationMiddlewareBuilder":
        """Append a single rule to the builder's pending rule list.

        Args:
            rule: The :class:`IValidationRule` to add to the in-flight
                rule list of this builder.

        Returns:
            This builder, to support chained ``with_rule`` calls.
        """
        self._rules.append(rule)
        return self

    def with_rules(self, rules: Sequence[IValidationRule]) -> "RequestValidationMiddlewareBuilder":
        """Extend the builder's pending rule list with a sequence of rules.

        Args:
            rules: A sequence of :class:`IValidationRule` instances to
                append to the builder's pending rule list.

        Returns:
            This builder, to support chained ``with_rules`` calls.
        """
        self._rules.extend(rules)
        return self

    def build(self) -> RequestValidationMiddleware:
        """Materialize a :class:`RequestValidationMiddleware` from the builder.

        Returns:
            A :class:`RequestValidationMiddleware` whose rule list is a
            fresh copy of the rules accumulated on this builder.
        """
        return RequestValidationMiddleware(rules=self._rules)

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "RequestValidationMiddlewareBuilder"


__all__ = ["IValidationRule", "RequestValidationMiddleware", "RequestValidationMiddlewareBuilder"]

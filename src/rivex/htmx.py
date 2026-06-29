from __future__ import annotations

from typing import Any

from rivex.responses import HTMLResponse


__all__ = (
    "HtmxDetails",
    "HtmxResponse",
    "HXRedirect",
    "HXRefresh",
    "HXLocation",
    "HXSwap",
    "HXRetarget",
    "HXReselect",
    "HXPushUrl",
)


class HtmxDetails:
    """Describes the HTMX state of the current request.

    Every attribute is ``None`` when the request is **not** an HTMX
    request (i.e. the ``HX-Request`` header is absent or ``"false"``).
    """

    __slots__ = (
        "_request",
        "_parsed",
        "_boosted",
        "_current_url",
        "_history_restore_request",
        "_prompt",
        "_target",
        "_trigger",
        "_trigger_name",
    )

    def __init__(self, request: Any) -> None:
        self._request = request
        self._parsed = False
        self._boosted: bool | None = None
        self._current_url: str | None = None
        self._history_restore_request: bool | None = None
        self._prompt: str | None = None
        self._target: str | None = None
        self._trigger: str | None = None
        self._trigger_name: str | None = None

    def _ensure(self) -> None:
        if self._parsed:
            return
        self._parsed = True
        hdr = self._request._headers.get
        raw = hdr("hx-request", "")
        if raw.lower() not in ("true", "1"):
            return
        val = hdr("hx-boosted", "")
        if val:
            self._boosted = val.lower() in ("true", "1")
        val = hdr("hx-current-url", "")
        if val:
            self._current_url = val
        val = hdr("hx-history-restore-request", "")
        if val:
            self._history_restore_request = val.lower() in ("true", "1")
        self._prompt = hdr("hx-prompt") or None
        self._target = hdr("hx-target") or None
        self._trigger = hdr("hx-trigger") or None
        self._trigger_name = hdr("hx-trigger-name") or None

    @property
    def request(self) -> bool:
        """``True`` when the current request is an HTMX request."""
        self._ensure()
        raw = self._request._headers.get("hx-request", "")
        return raw.lower() in ("true", "1")

    @property
    def boosted(self) -> bool | None:
        """``HX-Boosted`` — ``True`` when the request is boosted."""
        self._ensure()
        return self._boosted

    @property
    def current_url(self) -> str | None:
        """``HX-Current-URL`` — the current page URL."""
        self._ensure()
        return self._current_url

    @property
    def history_restore_request(self) -> bool | None:
        """``HX-History-Restore-Request`` — ``True`` on history restore."""
        self._ensure()
        return self._history_restore_request

    @property
    def prompt(self) -> str | None:
        """``HX-Prompt`` — the user's prompt response."""
        self._ensure()
        return self._prompt

    @property
    def target(self) -> str | None:
        """``HX-Target`` — the CSS selector of the target element."""
        self._ensure()
        return self._target

    @property
    def trigger(self) -> str | None:
        """``HX-Trigger`` — the ID of the trigger element."""
        self._ensure()
        return self._trigger

    @property
    def trigger_name(self) -> str | None:
        """``HX-Trigger-Name`` — the name of the trigger element."""
        self._ensure()
        return self._trigger_name


class HtmxResponse(HTMLResponse):
    """An HTML response that also sends HTMX response headers.

    Example::

        from rivex.htmx import HtmxResponse

        return HtmxResponse(
            "<div>Hello</div>",
            trigger="itemUpdated",
            redirect="/thanks",
        )
    """

    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        *,
        trigger: str | None = None,
        after_settle: str | None = None,
        after_swap: str | None = None,
        push_url: str | bool | None = None,
        redirect: str | None = None,
        refresh: bool | None = None,
        replace_url: str | None = None,
        reswap: str | None = None,
        retarget: str | None = None,
        reselect: str | None = None,
    ) -> None:
        h = dict(headers) if headers else {}
        if trigger is not None:
            h["hx-trigger"] = trigger
        if after_settle is not None:
            h["hx-trigger-after-settle"] = after_settle
        if after_swap is not None:
            h["hx-trigger-after-swap"] = after_swap
        if push_url is not None:
            h["hx-push-url"] = "true" if push_url is True else ("false" if push_url is False else push_url)
        if redirect is not None:
            h["hx-redirect"] = redirect
        if refresh is not None:
            h["hx-refresh"] = "true" if refresh else "false"
        if replace_url is not None:
            h["hx-replace-url"] = replace_url
        if reswap is not None:
            h["hx-reswap"] = reswap
        if retarget is not None:
            h["hx-retarget"] = retarget
        if reselect is not None:
            h["hx-reselect"] = reselect
        super().__init__(content=content, status_code=status_code, headers=h or None)


def HXRedirect(
    url: str,
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Redirect the client via an HTMX response header."""
    return HtmxResponse(content=content, status_code=status_code, headers=headers, redirect=url)


def HXRefresh(
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Tell HTMX to refresh the current page."""
    return HtmxResponse(content=content, status_code=status_code, headers=headers, refresh=True)


def HXLocation(
    url: str,
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Tell HTMX to navigate to a new URL (like client-side redirect)."""
    return HtmxResponse(content=content, status_code=status_code, headers=headers, redirect=url)


def HXSwap(
    swap_spec: str,
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Override the swap strategy for this response."""
    return HtmxResponse(content=content, status_code=status_code, headers=headers, reswap=swap_spec)


def HXRetarget(
    target: str,
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Retarget the swap target for this response."""
    return HtmxResponse(
        content=content, status_code=status_code, headers=headers, retarget=target
    )


def HXReselect(
    selector: str,
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Reselect content to swap from the response."""
    return HtmxResponse(
        content=content, status_code=status_code, headers=headers, reselect=selector
    )


def HXPushUrl(
    url: str | bool,
    content: str = "",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HtmxResponse:
    """Push a URL into the browser history."""
    return HtmxResponse(content=content, status_code=status_code, headers=headers, push_url=url)

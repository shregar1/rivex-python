from __future__ import annotations

import gettext as _gettext
import os
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

_current_locale: ContextVar[str] = ContextVar("rivex_locale", default="en")
_current_domain: ContextVar[str] = ContextVar("rivex_domain", default="messages")


def set_locale(locale: str) -> None:
    _current_locale.set(locale)


def get_locale() -> str:
    return _current_locale.get()


class Translations:
    """Translation catalog loaded from .mo files.

    Uses standard GNU gettext directory layout::

        locale/
            en/LC_MESSAGES/messages.mo
            fr/LC_MESSAGES/messages.mo
            de/LC_MESSAGES/messages.mo
    """

    def __init__(self, locale_dir: str | Path, domain: str = "messages"):
        self._locale_dir = Path(locale_dir)
        self._domain = domain
        self._catalogs: dict[str, _gettext.GNUTranslations] = {}
        self._load_available()

    def _load_available(self) -> None:
        if not self._locale_dir.exists():
            return
        for lang_dir in self._locale_dir.iterdir():
            if lang_dir.is_dir():
                mo_path = lang_dir / "LC_MESSAGES" / f"{self._domain}.mo"
                if mo_path.exists():
                    try:
                        self._catalogs[lang_dir.name] = _gettext.GNUTranslations(
                            open(mo_path, "rb")
                        )
                    except Exception:
                        pass

    def available_locales(self) -> list[str]:
        return sorted(self._catalogs.keys())

    def gettext(self, message: str, locale: str | None = None) -> str:
        locale = locale or _current_locale.get()
        catalog = self._catalogs.get(locale)
        if catalog is None:
            return message
        return catalog.gettext(message)

    def ngettext(self, singular: str, plural: str, n: int, locale: str | None = None) -> str:
        locale = locale or _current_locale.get()
        catalog = self._catalogs.get(locale)
        if catalog is None:
            return singular if n == 1 else plural
        return catalog.ngettext(singular, plural, n)

    def pgettext(self, context: str, message: str, locale: str | None = None) -> str:
        locale = locale or _current_locale.get()
        catalog = self._catalogs.get(locale)
        if catalog is None:
            return message
        return catalog.pgettext(context, message)


def _get_intl() -> Translations | None:
    try:
        import rivex
        app = rivex._app_stack.get()
        return getattr(app.state, "_translations", None)
    except (ImportError, LookupError, AttributeError):
        return None


_ = _gettext_translate = _gettext


def gettext(message: str) -> str:
    t = _get_intl()
    if t is not None:
        return t.gettext(message)
    return message


def ngettext(singular: str, plural: str, n: int) -> str:
    t = _get_intl()
    if t is not None:
        return t.ngettext(singular, plural, n)
    return singular if n == 1 else plural


def pgettext(context: str, message: str) -> str:
    t = _get_intl()
    if t is not None:
        return t.pgettext(context, message)
    return message


class LocaleMiddleware:
    """Detects user locale from Accept-Language header and sets
    ``request.state.locale`` and the context var for ``gettext()``.

    Usage::

        app.add_middleware(LocaleMiddleware, default_locale="en")

    Supports cookie override via ``X-Locale`` header or ``locale``
    query parameter for testing.
    """

    def __init__(
        self,
        default_locale: str = "en",
        translations: Translations | None = None,
        cookie_name: str = "rivex_locale",
    ):
        self._default_locale = default_locale
        self._translations = translations
        self._cookie_name = cookie_name

        import re
        self._re = re

    def _parse_accept_language(self, header: str) -> list[str]:
        locales: list[tuple[str, float]] = []
        for part in header.split(","):
            part = part.strip()
            if not part:
                continue
            if ";" in part:
                locale, q = part.split(";", 1)
                q = q.strip()
                if q.startswith("q="):
                    try:
                        q_val = float(q[2:])
                    except ValueError:
                        q_val = 1.0
                else:
                    q_val = 1.0
            else:
                locale = part
                q_val = 1.0
            locales.append((locale.split("-")[0], q_val))
        locales.sort(key=lambda x: -x[1])
        return [loc for loc, _ in locales]

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        headers = request_data.get("headers", {})
        locale = self._default_locale

        # 1. Query param override
        query = request_data.get("query_string", "")
        if query and self._re.search(r"(^|&)locale=([^&]+)", query):
            m = self._re.search(r"(^|&)locale=([^&]+)", query)
            if m:
                locale = m.group(2)

        # 2. Cookie override
        if locale == self._default_locale:
            cookies = request_data.get("cookies", "")
            if isinstance(cookies, str):
                m = self._re.search(f"{self._cookie_name}=([^;]+)", cookies)
                if m:
                    locale = m.group(1)

        # 3. Accept-Language
        if locale == self._default_locale:
            accept = (headers.get("accept-language") if isinstance(headers, dict)
                      else None) or ""
            if accept:
                preferred = self._parse_accept_language(accept)
                if self._translations:
                    available = set(self._translations.available_locales())
                    for lang in preferred:
                        if lang in available:
                            locale = lang
                            break

        # Update context var
        _current_locale.set(locale)

        # Store in request state
        request_data = dict(request_data)
        state = request_data.get("state", {})
        if isinstance(state, dict):
            request_data["state"] = {**state, "locale": locale}

        result: dict = await call_next(request_data)

        # Add Content-Language header
        existing = result.get("headers", {})
        if isinstance(existing, dict):
            result = dict(result) if result is not None else {}
            result["headers"] = {**existing, "Content-Language": locale}
        return result


def format_number(number: float, locale: str | None = None, decimals: int = 2) -> str:
    """Format a number with locale-appropriate separators."""
    locale = locale or _current_locale.get()
    formatted = f"{number:.{decimals}f}"
    if locale in ("de", "fr", "it", "es", "pt", "nl"):
        integer_part, _, frac = formatted.partition(".")
        integer_part = integer_part.replace(",", ".")
        formatted = f"{integer_part},{frac}"
    return formatted


def format_date(year: int, month: int, day: int, locale: str | None = None) -> str:
    """Format a date in locale-appropriate format."""
    locale = locale or _current_locale.get()
    month_names = {
        "en": ["January","February","March","April","May","June","July","August","September","October","November","December"],
        "fr": ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"],
        "de": ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],
        "es": ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],
    }
    names = month_names.get(locale, month_names["en"])
    if locale == "en":
        return f"{month_names['en'][month-1]} {day}, {year}"
    elif locale in ("fr", "de", "es", "it", "nl"):
        return f"{day}. {names[month-1]} {year}"
    return f"{year}-{month:02d}-{day:02d}"


def format_currency(amount: float, currency: str = "USD", locale: str | None = None) -> str:
    locale = locale or _current_locale.get()
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "₹"}
    sym = symbols.get(currency, currency + " ")
    n = format_number(amount, locale, decimals=2 if currency != "JPY" else 0)
    return f"{sym}{n}"

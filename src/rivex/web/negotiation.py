from __future__ import annotations

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc


def parse_accept(accept_header: str) -> list[tuple[str, float]]:
    """Parse Accept header into sorted list of (media_type, quality) tuples."""
    if HAS_CORE:
        return [(media, round(float(q), 3)) for media, q in _rc.parse_accept(accept_header)]

    types: list[tuple[str, float]] = []
    for item in accept_header.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(";")
        media = parts[0].strip()
        q = 1.0
        for param in parts[1:]:
            param = param.strip()
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    pass
        types.append((media, q))
    types.sort(key=lambda x: x[1], reverse=True)
    return types


def best_match(accept_header: str, available: list[str]) -> str | None:
    """Return the best matching content type from available list, or None."""
    if HAS_CORE:
        result: str | None = _rc.best_match(accept_header, available)
        return result

    if not accept_header:
        return available[0] if available else None
    parsed = parse_accept(accept_header)
    for media, _ in parsed:
        if media in available:
            return media
        if media == "*/*":
            return available[0] if available else None
        main = media.split("/")[0]
        if media.endswith("/*"):
            for avail in available:
                if avail.startswith(main + "/"):
                    return avail
    return None

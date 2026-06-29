"""Display-name helpers for public profiles."""


def public_display_name(first_name: str, last_name: str) -> str:
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first:
        return "Member"
    if not last:
        return first
    return f"{first} {last[0]}."

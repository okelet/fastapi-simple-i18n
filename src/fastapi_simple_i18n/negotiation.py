"""
Accept-Language parsing and locale negotiation utilities.
"""


def parse_accept_language(header: str) -> list[str]:
    """
    Parse an ``Accept-Language`` header into locale codes sorted by quality.

    Example:
        ``"es-ES,es;q=0.9,en;q=0.8"`` becomes ``["es-ES", "es", "en"]``.
    """
    if not header:
        return []

    locales_with_quality: list[tuple[str, float]] = []
    for raw_part in header.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ";q=" in part:
            lang, q_str = part.split(";q=", 1)
            try:
                quality = float(q_str.strip())
            except ValueError:
                quality = 0.0
        else:
            lang = part
            quality = 1.0
        locales_with_quality.append((lang.strip(), quality))

    locales_with_quality.sort(key=lambda item: item[1], reverse=True)
    return [loc for loc, _ in locales_with_quality]


def negotiate_locale(accept_language: str, supported_locales: set[str], default_locale: str) -> str:
    """
    Pick the best supported locale for an ``Accept-Language`` header.

    Resolution order:

    1. Exact match against a supported locale (case-insensitive).
    2. Base language match (e.g. ``"es-ES"`` matches supported ``"es"``).
    3. The provided ``default_locale``.

    Args:
        accept_language: The raw header value.
        supported_locales: Locales the application can serve.
        default_locale: Locale returned when nothing matches.
    """
    normalized_supported = {loc.lower(): loc for loc in supported_locales}

    for candidate in parse_accept_language(accept_language):
        normalized = candidate.lower().replace("_", "-")
        if normalized in normalized_supported:
            return normalized_supported[normalized]
        base = normalized.split("-")[0]
        if base in normalized_supported:
            return normalized_supported[base]

    return default_locale

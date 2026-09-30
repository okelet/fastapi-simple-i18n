"""
Accept-Language parsing and locale negotiation utilities.

Negotiation returns a :class:`babel.core.Locale`, so the middleware and
everything downstream work with the same value type as the rest of the library.
Header entries that are not locales (``*``, ``en-*``, a typo) are skipped rather
than treated as a match.
"""

from collections.abc import Iterable

from .locale import Locale, resolve_locale


def parse_accept_language(header: str) -> list[str]:
    """
    Parse an ``Accept-Language`` header into locale codes sorted by quality.

    The codes are returned exactly as they were written, because a header is a
    list of preferences, not a list of validated locales: it may carry ``*`` or
    a malformed entry that :func:`negotiate_locale` must skip. Use
    :func:`~fastapi_simple_i18n.locale.resolve_locale` to resolve one of the
    results.

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


def negotiate_locale(
    accept_language: str,
    supported_locales: Iterable[str | Locale],
    default_locale: str | Locale,
) -> Locale:
    """
    Pick the best supported locale for an ``Accept-Language`` header.

    Candidates are tried in quality order, and for each one:

    1. An exact match against a supported locale. Matching ignores spelling:
       ``es_ES``, ``es-ES`` and ``es-es`` all select the supported ``es``.
    2. The candidate's base language, but only when a supported locale *is*
       that bare language (``es-ES`` selects a supported ``es``, never a
       supported ``es-MX``, since picking a region the client did not ask for
       is a guess).

    Candidates that are not valid locale tags (``*``, ``en-*``, typos) are
    skipped, and the default locale is returned when nothing matches.

    Args:
        accept_language: The raw header value.
        supported_locales: Locales the application can serve.
        default_locale: Locale returned when nothing matches.

    Returns:
        The negotiated :class:`babel.core.Locale`.

    Raises:
        ValueError: If a supported locale or the default locale is not a valid
            locale tag.
    """
    supported = [resolve_locale(locale) for locale in supported_locales]
    exact = {locale: locale for locale in supported}
    # Only locales that are nothing but a language can answer a regional
    # candidate, so that a request for ``es-ES`` never lands on ``es-MX``.
    by_language = {locale.language: locale for locale in supported if str(locale) == locale.language}

    for candidate in parse_accept_language(accept_language):
        try:
            parsed = resolve_locale(candidate)
        except ValueError:
            continue
        match = exact.get(parsed)
        if match is not None:
            return match
        match = by_language.get(parsed.language)
        if match is not None:
            return match

    return resolve_locale(default_locale)

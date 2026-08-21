"""Variable builders for coaching chat-route prompt."""

from __future__ import annotations

from mc_foundation.locale import locale_display_name


def build_coaching_chat_route_variables(
    *,
    question: str,
    lang: str,
) -> dict[str, str]:
    return {
        "lang_label": locale_display_name(lang),
        "lang": lang,
        "question": question,
    }

"""Value formatting shared by cards, tables and charts."""

from __future__ import annotations

import html
import re
from typing import Any, Optional


def esc(value: Any) -> str:
    """Escape untrusted text before interpolating into ``st.html``.

    ``st.html`` escapes nothing, so every account name, meeting title and model-authored
    string must pass through here.
    """
    return html.escape("" if value is None else str(value), quote=True)


def money(value: Optional[float], precise: bool = False) -> str:
    if value is None:
        return "n/a"
    v = float(value)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if precise:
        return "{}${:,.0f}".format(sign, a)
    if a >= 1_000_000:
        return "{}${:.2f}M".format(sign, a / 1_000_000).replace(".00M", "M")
    if a >= 1_000:
        return "{}${:,.0f}K".format(sign, a / 1_000)
    return "{}${:,.0f}".format(sign, a)


def percent(value: Optional[float], digits: int = 1) -> str:
    return "n/a" if value is None else "{:.{d}f}%".format(float(value), d=digits)


def multiple(value: Optional[float]) -> str:
    return "n/a" if value is None else "{:.1f}x".format(float(value))


def count(value: Optional[float]) -> str:
    return "n/a" if value is None else "{:,.0f}".format(float(value))


def by_unit(value: Optional[float], unit: str, precise: bool = False) -> str:
    if unit == "$":
        return money(value, precise=precise)
    if unit == "%":
        return percent(value)
    if unit == "x":
        return multiple(value)
    return count(value)


def initials(full_name: str) -> str:
    parts = [p for p in re.split(r"\s+", (full_name or "").strip()) if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def first_name(full_name: str) -> str:
    return (full_name or "").strip().split(" ")[0] if full_name else ""


def truncate(text: str, limit: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def short_sentence(text: str, max_words: int = 14) -> str:
    """A card subtitle: one plain sentence, no parenthetical asides.

    Every built-in subtitle is one short sentence of business English, and the
    subtitle slot is 11.5px with room for about a dozen words. Model-authored
    descriptions run past that and carry column names in brackets, so a created
    card ends up reading nothing like the card beside it. The full text stays in
    ``description``, which is what the info panel shows; the card gets this.

    Trailing clauses go before the sentence is chopped mid-word: a description
    that ends "..., plus a month over month comparison" is describing the delta
    pill, which the tile already draws.
    """
    cleaned = re.sub(r"\s*\([^)]*\)", "", (text or "").replace("\n", " "))
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned:
        return ""

    cleaned = re.split(r"(?<=[.!?])\s", cleaned)[0].strip()
    if len(cleaned.split(" ")) > max_words:
        clause = cleaned.split(", ")[0].strip()
        if 3 <= len(clause.split(" ")) <= max_words:
            cleaned = clause
    words = cleaned.split(" ")
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words])
    return cleaned.rstrip(" ,;:.") + "."


def humanize_column(name: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", str(name)).strip()
    small = {"by", "of", "vs", "to", "per", "and"}
    words = [w if w.isupper() else (w if w.lower() in small else w.capitalize())
             for w in cleaned.split(" ")]
    if words:
        words[0] = words[0].capitalize() if not words[0].isupper() else words[0]
    return " ".join(words)

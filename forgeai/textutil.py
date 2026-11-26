"""Deterministic text helpers shared by the eval generator, the judge and the guard.

Everything here is pure Python with no LLM involved. These functions are the
"distrust" layer: whenever an LLM claims a quote exists, a fact is present or a
number is grounded, one of these functions checks the claim against real text.
"""
from __future__ import annotations

import re
from rapidfuzz import fuzz

STOPWORDS = set(
    """a an the and or but if of to in on at by for with from into onto over under as is are was were be been
    being am do does did doing have has had having i me my we our you your he she it its they them their this that
    these those there here what which who whom whose when where why how all any both each few more most other some
    such no nor not only own same so than too very can could will would shall should may might must just also
    about above after again against before below between during out off up down further then once per via etc
    please tell know want need get got let s t""".split()
)

_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "−": "-", " ": " ", "•": " ", "­": "",
})


def normalize(text: str) -> str:
    """Lowercase, unify quotes/dashes, collapse whitespace."""
    text = (text or "").translate(_TRANSLATE).lower()
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    """Word tokens that keep IDs (sp-1042), decimals (45.50) and codes (a/b) intact."""
    return re.findall(r"[a-z0-9]+(?:[.\-/_][a-z0-9]+)*", normalize(text))


def stem(word: str) -> str:
    """A tiny suffix-stripping stemmer. Crude, but enough to match approval/approved."""
    for suffix in ("ations", "ation", "ments", "ment", "ingly", "ings", "ing", "ies", "ied", "ers", "er",
                   "edly", "ed", "es", "als", "al", "ions", "ion", "ly", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content_tokens(text: str) -> set[str]:
    """Stemmed, stopword-free tokens (numbers excluded; they are checked separately)."""
    out = set()
    for tok in tokens(text):
        if tok in STOPWORDS or is_number_token(tok):
            continue
        if len(tok) < 2:
            continue
        out.add(stem(tok))
    return out


def is_number_token(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", tok.replace(",", "")))


def _canon_number(raw: str) -> str | None:
    raw = raw.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def extract_numbers(text: str) -> set[str]:
    """All numbers in canonical form. '1,200' -> '1200', '$45.50' -> '45.5', 'fifteen' -> '15'.

    Digits glued to letters (part numbers such as 'HX-2040') are ignored here; those are
    handled by extract_ids so a part number is never mistaken for a quantity.
    """
    text = (text or "").translate(_TRANSLATE)
    found: set[str] = set()
    # Lookbehinds: not glued to a letter/digit/decimal point, and not the digit half of an
    # ID such as "HX-2040" or "A/12". Ranges like "10-15" still yield both 10 and 15.
    for m in re.finditer(r"(?<![A-Za-z0-9.])(?<![A-Za-z]-)(?<![A-Za-z]/)\$?\d[\d,]*(?:\.\d+)?%?(?![A-Za-z0-9])", text):
        canon = _canon_number(m.group(0))
        if canon is not None:
            found.add(canon)
    low = text.lower()
    for m in re.finditer(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[- ](one|two|three|four|five|six|seven|eight|nine)\b", low):
        found.add(str(_NUM_WORDS[m.group(1)] + _NUM_WORDS[m.group(2)]))
    for word, value in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            found.add(str(value))
    return found


def is_id_token(tok: str) -> bool:
    """Identifier-like token: starts with a letter and contains a digit (HX-2040, RFQ22, SMS-F-071).

    Tokens that start with a digit ("24-month", "30-day") are quantities, not IDs.
    """
    return len(tok) >= 3 and bool(re.fullmatch(r"[a-z][a-z0-9\-_/.]*\d[a-z0-9\-_/.]*", tok))


def extract_ids(text: str) -> set[str]:
    """All identifier-like tokens in a text (see is_id_token)."""
    return {tok for tok in tokens(text) if is_id_token(tok)}


def overlap(a: set[str], b: set[str]) -> float:
    """Fraction of `a` found in `b` (1.0 when `a` is empty)."""
    if not a:
        return 1.0
    return len(a & b) / len(a)


def contains_quote(quote: str, text: str, threshold: int = 90) -> bool:
    """True if `quote` appears in `text`, verbatim after normalisation or near-verbatim (fuzzy)."""
    q, t = normalize(quote), normalize(text)
    if not q:
        return False
    if q in t:
        return True
    # strip punctuation and retry (PDF extraction often mangles punctuation/spacing)
    q2 = re.sub(r"[^a-z0-9 ]", "", q)
    t2 = re.sub(r"[^a-z0-9 ]", "", t)
    if q2 and q2 in t2:
        return True
    if len(q2) < 15:
        return False
    # Fuzzy match tolerates PDF spacing glitches, but NEVER a changed number or ID:
    # numbers/IDs in the quote must occur exactly in the aligned window of the text.
    al = fuzz.partial_ratio_alignment(q2, t2)
    if al is None or al.score < threshold:
        return False
    window = t2[max(0, al.dest_start - 5): al.dest_end + 5]
    return extract_numbers(q2) <= extract_numbers(window) and extract_ids(q2) <= extract_ids(window)


def fact_in_text(fact: str, text: str) -> bool:
    """Is a short expected fact present in a text?

    Numbers and IDs in the fact must match exactly (no fuzzy numbers). The remaining words
    must overlap enough: generous when the fact is anchored by a number, stricter otherwise.
    """
    f_nums, t_nums = extract_numbers(fact), extract_numbers(text)
    f_ids, t_ids = extract_ids(fact), extract_ids(text)
    if not f_nums <= t_nums or not f_ids <= t_ids:
        return False
    f_words = content_tokens(fact) - {stem(i) for i in f_ids}
    t_words = content_tokens(text)
    if f_nums or f_ids:
        return len(f_words) <= 2 or overlap(f_words, t_words) >= 0.34
    if overlap(f_words, t_words) >= 0.6:
        return True
    return fuzz.partial_ratio(normalize(fact), normalize(text)) >= 88


def fact_recall(facts: list[str], text: str) -> tuple[float, list[str]]:
    """Fraction of facts found in text, plus the list of missing facts."""
    if not facts:
        return 1.0, []
    missing = [f for f in facts if not fact_in_text(f, text)]
    return 1 - len(missing) / len(facts), missing


# ---- refusals -------------------------------------------------------------------------

_REFUSAL_PATTERNS = [
    r"\b(i|we) (do not|don't|cannot|can't|am unable to|are unable to) (have|find|answer|help|provide|locate|see|assist)",
    r"\b(not|isn't|is not|aren't|are not) (covered|mentioned|specified|included|available|addressed|stated|found|provided)\b.{0,40}\b(document|context|polic|source|information|material)",
    r"\b(no|not enough) (information|details|data) (about|on|regarding|in)\b",
    r"\boutside (of )?(my|the|this) (scope|remit)",
    r"\b(unable|not able) to (answer|help|provide)",
    r"\b(does not|doesn't|do not|don't|did not|didn't) (contain|include|mention|cover|specify|provide|say|state|address)\b",
    r"\b(there is|there's) no (information|mention|detail)",
]


def is_refusal(answer: str, refusal_phrase: str) -> bool:
    """Did the agent decline? Requires a refusal signal AND little other substance.

    A partial answer ("X is 21 days; the documents don't cover Y") is an answer, not a refusal.
    """
    norm = normalize(answer)
    if not norm:
        return True
    phrase = normalize(refusal_phrase)
    # Opening with the exact refusal sentence is a refusal, whatever explanation follows it.
    if phrase and fuzz.partial_ratio(phrase, norm[: len(phrase) + 15]) >= 92:
        return True
    signal = bool(phrase) and (phrase in norm or fuzz.partial_ratio(phrase, norm) >= 88)
    if not signal:
        signal = any(re.search(p, norm) for p in _REFUSAL_PATTERNS)
    if not signal:
        return False
    # Remove the refusal sentence(s) and see how much substance is left.
    sentences = re.split(r"(?<=[.!?\]])\s+", norm)
    substantive = [
        s for s in sentences
        if not (phrase and fuzz.partial_ratio(phrase, s) >= 85) and not any(re.search(p, s) for p in _REFUSAL_PATTERNS)
    ]
    leftover = " ".join(substantive)
    cites_something = "[source" in leftover
    n_words = len(re.sub(r"\[source:[^\]]*\]", "", leftover).split())
    # A cited sentence is a (partial) answer; an uncited remark ("contact the helpdesk") is part of a refusal.
    return n_words < 8 or (n_words < 25 and not cites_something)


def word_count(text: str) -> int:
    return len(re.sub(r"\[source:[^\]]*\]", "", text or "").split())


def truncate(text: str, max_chars: int) -> str:
    text = text or ""
    return text if len(text) <= max_chars else text[: max_chars - 3].rstrip() + "..."

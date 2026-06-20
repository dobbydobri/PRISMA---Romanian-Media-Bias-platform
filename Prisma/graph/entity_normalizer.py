from __future__ import annotations

import re
import logging
import unicodedata
from collections import defaultdict, Counter
from typing import Iterable

logger = logging.getLogger(__name__)


# ── Pass 0 — Unicode: cedilla → comma-below + NFC ────────────────────────────

_ROMANIAN_CHAR_MAP = str.maketrans({
    '\u015f': '\u0219',  # ş → ș
    '\u015e': '\u0218',  # Ş → Ș
    '\u0163': '\u021b',  # ţ → ț
    '\u0162': '\u021a',  # Ţ → Ț
})


def normalize_unicode(text: str) -> str:
    """Normalize to NFC and fix Romanian cedilla → comma-below."""
    text = unicodedata.normalize('NFC', text)
    text = text.translate(_ROMANIAN_CHAR_MAP)
    return text


# ── Pass 2 — Override table (safety net for lemmatizer failures) ──────────────

_LEMMA_OVERRIDES: dict[str, str] = {
    # Add entries here after first run inspection.
    # Example: if spaCy produces "româniei" instead of "România":
    # "româniei": "România",
}


def apply_lemma_override(lemma: str) -> str:
    """Apply manual override if the lemmatizer produced an incorrect form."""
    key = lemma.lower().strip()
    if key in _LEMMA_OVERRIDES:
        return _LEMMA_OVERRIDES[key]
    return lemma


# ── Pass 1/3 — Synonym table (acronym ↔ expansion merges) ────────────────────

_SYNONYM_TABLE: dict[str, str] = {
    "ue": "Uniunea Europeană",
    "uniunea europeană": "Uniunea Europeană",
    "uniunii europene": "Uniunea Europeană",

    "sua": "Statele Unite",
    "statele unite": "Statele Unite",
    "statelor unite": "Statele Unite",
    "statele unite ale americii": "Statele Unite",
    "statelor unite ale americii": "Statele Unite",

    "onu": "ONU",
    "organizația națiunilor unite": "ONU",
    "organizației națiunilor unite": "ONU",

    "oms": "OMS",
    "organizația mondială a sănătății": "OMS",

    "bce": "BCE",
    "banca centrală europeană": "BCE",
    "băncii centrale europene": "BCE",

    "ce": "Comisia Europeană",
    "comisia europeană": "Comisia Europeană",
    "comisiei europene": "Comisia Europeană",

    "pe": "Parlamentul European",
    "parlamentul european": "Parlamentul European",
    "parlamentului european": "Parlamentul European",

    "partidul social democrat": "PSD",
    "partidului social democrat": "PSD",
    "partidul național liberal": "PNL",
    "partidului național liberal": "PNL",
    "uniunea salvați românia": "USR",
    "alianța pentru unirea românilor": "AUR",
    "alianței pentru unirea românilor": "AUR",
    "uniunea democrată maghiară din românia": "UDMR",

    "direcția națională anticorupție": "DNA",
    "direcției naționale anticorupție": "DNA",
    "serviciul român de informații": "SRI",
    "serviciului român de informații": "SRI",
    "curtea constituțională": "CCR",
    "curtea constituțională a româniei": "CCR",
    "curții constituționale": "CCR",
    "banca națională a româniei": "BNR",
    "băncii naționale a româniei": "BNR",
    "consiliul superior al magistraturii": "CSM",
    "consiliului superior al magistraturii": "CSM",
    "agenția națională de administrare fiscală": "ANAF",
    "serviciul de telecomunicații speciale": "STS",
    "inspectoratul general al poliției române": "IGPR",

    "organizația tratatului atlanticului de nord": "NATO"
}


def normalize_synonym(text: str) -> str:
    """Merge acronyms and their expansions to a single canonical form."""
    key = text.lower().strip()
    if key in _SYNONYM_TABLE:
        return _SYNONYM_TABLE[key]
    return text


# ── Pass 4 — Title prefix stripping ──────────────────────────────────────────

LEADING_TITLES_SINGLE: frozenset[str] = frozenset({
    "președintele", "președinte",
    "premierul", "premier",
    "ministrul", "ministra", "ministru",
    "vicepremierul",
    "senatorul", "senatoarea", "senator", "senatoare",
    "deputatul", "deputata", "deputat", "deputată",
    "primarul", "primar",
    "guvernatorul", "guvernatoarea",
    "consilierul",
    "miliardarul",
    "domnul", "doamna", "dl", "dna",
    "profesor", "profesoara", "profesorul", "prof",
    "doctor", "doctorul", "doctoriță", "dr",
    "academicianul",
    "generalul", "general",
    "colonelul", "colonel",
    "capitanul", "capitan",
    "locotenentul", "locotenent",
    "judecătorul", "judecătoarea",
    "procurorul", "procuroarea",
    "ambasadorul", "ambasadoarea",
    "regele", "regina",
    "principele", "principesa", "prințul",
    "papa", "patriarhul", "părintele", "preotul",
})

LEADING_TITLES_DOUBLE: frozenset[str] = frozenset({
    "fostul președinte", "fosta președintă",
    "fostul premier",
    "fostul ministru", "fosta ministră",
    "fostul primar", "fosta primar",
    "prim-ministrul", "prim-ministru",
    "ex-președintele",
    "ex-premier",
    "ex-ministrul",
    "viceprim-ministrul", "vice-premier"
})

TRAILING_TITLES: frozenset[str] = frozenset({
    "președinte", "președintele",
    "premier", "premierul",
    "ministru", "ministrul",
    "senator", "deputat", "primar",
    "ex-președinte", "ex-premier", "ex-ministru",
    "fost președinte", "fost premier",
})

_MINISTRY_PREFIX_RE = re.compile(
    r'^(?:Ministrul|Ministra)\s+[\w\-]+(?:\s+[\w\-]+)?,\s*',
    re.UNICODE,
)

_INTERIMAR_PREFIX_RE = re.compile(
    r'^(?:Președintele|Premierul|Prim-ministrul)\s+interimar\s+',
    re.UNICODE | re.IGNORECASE,
)

_WHITESPACE_RE = re.compile(r'\s+')
_EDGE_PUNCT_RE = re.compile(r'^[\s.,;:\-"\'`«»()\[\]]+|[\s.,;:\-"\'`«»()\[\]]+$')


def strip_title_prefix(text: str) -> str:
    """
    Strip Romanian title prefixes and clean edge punctuation.

    Handles:
    - Single-token prefixes: "Premierul Marcel Ciolacu" → "Marcel Ciolacu"
    - Double-token prefixes: "Fostul premier Marcel Ciolacu" → "Marcel Ciolacu"
    - Interimar pattern: "Președintele interimar Ilie Bolojan" → "Ilie Bolojan"
    - Ministry pattern: "Ministrul Energiei, Sebastian Burduja" → "Sebastian Burduja"
    - Trailing title: "Iohannis, președinte" → "Iohannis"
    - Stacked prefixes: up to 3 iterations
    """
    if not text:
        return text

    text = unicodedata.normalize('NFC', text)
    text = _WHITESPACE_RE.sub(' ', text).strip()
    text = _EDGE_PUNCT_RE.sub('', text)
    if not text:
        return text

    m = _MINISTRY_PREFIX_RE.match(text)
    if m:
        text = text[m.end():]

    m = _INTERIMAR_PREFIX_RE.match(text)
    if m:
        text = text[m.end():]

    for _ in range(3):
        tokens = text.split()
        if len(tokens) < 2:
            break

        if len(tokens) >= 3:
            two = f"{tokens[0]} {tokens[1]}".lower()
            if two in LEADING_TITLES_DOUBLE:
                text = ' '.join(tokens[2:])
                continue

        one = tokens[0].lower().rstrip('.')
        if one in LEADING_TITLES_SINGLE:
            text = ' '.join(tokens[1:])
            continue

        break

    if ',' in text:
        head, _, tail = text.rpartition(',')
        tail_norm = tail.strip().lower()
        if tail_norm in TRAILING_TITLES and head.strip():
            text = head.strip()

    text = _WHITESPACE_RE.sub(' ', text).strip()
    text = _EDGE_PUNCT_RE.sub('', text)

    return text


# ── Pass 5 — Surname → full-name merge (article-context-dependent) ────────────

def normalize_surname_in_context(
    entity_text: str,
    entity_label: str,
    article_entities: list[tuple[str, str]],
) -> str:
    """
    Merge standalone surnames to full names using article context.

    Rules:
    - Only applies to single-token PERSON entities
    - Looks for multi-token PERSON entities in the same article
      whose LAST token matches the surname
    - If exactly 1 candidate: merge (unambiguous)
    - If 0 or 2+ candidates: keep as-is (ambiguous or no match)

    Examples from corpus:
    - Article with only "Donald Trump": "Trump" → "Donald Trump" ✓
    - Article with "Donald Trump" AND "Melania Trump": "Trump" stays "Trump" ✗
    - Article with "Ludovic Orban" AND "Viktor Orban": "Orban" stays "Orban" ✗
    - Article with only "Marcel Ciolacu": "Ciolacu" → "Marcel Ciolacu" ✓
    """
    if entity_label != 'PERSON':
        return entity_text

    tokens = entity_text.strip().split()
    if len(tokens) != 1:
        return entity_text

    surname = tokens[0]

    candidates = list(set(
        text for text, label in article_entities
        if label == 'PERSON'
        and ' ' in text.strip()
        and text.strip().split()[-1] == surname
        and text.strip() != entity_text.strip()
    ))

    if len(candidates) == 1:
        return candidates[0]

    return entity_text


# ── Pass 6 — Token-order normalization ───────────────────────────────────────

def normalize_token_order(text: str) -> str:
    """
    Normalise token order for name variants like "Baștea Rodica" / "Rodica Baștea".

    Used both inside normalize_entity() (per-entity) and in build_canonical_map()
    (corpus-level) to group surface forms that share the same sorted-token key.
    The canonical form within each group is chosen by frequency in the corpus,
    so this function only produces the *grouping key*, not the final form.
    The actual rewrite to the most-frequent form happens in build_canonical_map().
    """
    return text


# ── Full normalization pipeline ───────────────────────────────────────────────

def normalize_entity(
    text: str,
    label: str = '',
    lemma: str | None = None,
    article_entities: list[tuple[str, str]] | None = None,
) -> str:
    """
    Full normalization pipeline.

    Args:
        text: Entity surface form from spaCy (ent.text)
        label: Entity label (PERSON, ORGANIZATION, GPE, etc.)
        lemma: Lemmatized form from spaCy (extract_entity_lemma output).
               Used as fallback when synonym table doesn't match.
        article_entities: All (text, label) pairs from same article,
                          needed for surname merge (pass 5). Already filtered
                          and normalized through passes 0-4.

    Corrected pipeline order:
        0. Unicode normalization (cedilla → comma-below, NFC)
        1. Synonym check on SURFACE form (catches multi-token inflections like
           "Uniunii Europene" → "Uniunea Europeană" BEFORE lemma destroys them)
        2. Lemma-based inflection resolution (only if no synonym match;
           handles single-token inflections like "României" → "România")
        3. Override table (safety net for lemmatizer failures)
        4. Title prefix stripping (existing logic, extended)
        5. Surname → full-name merge (article-context-dependent)
        6. Token-order normalization (corpus-level grouping key)
    """
    if not text:
        return ''

    result = normalize_unicode(text)

    synonym_result = normalize_synonym(result)
    if synonym_result != result:
        result = synonym_result
    else:
        if lemma:
            result = normalize_unicode(lemma)
        result = apply_lemma_override(result)

    result = strip_title_prefix(result)
    if not result:
        return ''

    if article_entities is not None:
        result = normalize_surname_in_context(result, label, article_entities)

    result = normalize_token_order(result)

    return result.strip()


# ── Corpus-wide canonicalization (token-order merging) ───────────────────────

def build_canonical_map(raw_surface_forms: Iterable[str]) -> dict[str, str]:
    """
    Build a raw-surface-form → canonical-form mapping for corpus-level
    token-order deduplication.

    Groups surface forms by their sorted-token key and picks the most
    frequently observed form as canonical. This resolves variants like
    "Baștea Rodica" / "Rodica Baștea" → whichever appears more often.

    Note: This operates on already-normalized forms (the output of
    normalize_entity() calls). It is NOT a replacement for normalize_entity().
    """
    groups: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    raw_to_normalized: dict[str, str] = {}

    for raw in raw_surface_forms:
        if not raw:
            continue
        normalized = normalize_entity(raw)
        if not normalized:
            continue
        raw_to_normalized[raw] = normalized

        tokens = tuple(sorted(t.lower() for t in normalized.split() if t))
        if not tokens:
            continue
        groups[tokens][normalized] += 1

    canonical_per_group: dict[tuple[str, ...], str] = {}
    for tokens, surface_counts in groups.items():
        ranked = sorted(
            surface_counts.items(),
            key=lambda x: (-x[1], -len(x[0]), x[0]),
        )
        canonical_per_group[tokens] = ranked[0][0]

    canonical_map: dict[str, str] = {}
    remapped = 0
    for raw, normalized in raw_to_normalized.items():
        tokens = tuple(sorted(t.lower() for t in normalized.split() if t))
        canonical = canonical_per_group.get(tokens, normalized)
        canonical_map[raw] = canonical
        if canonical != raw:
            remapped += 1

    raw_count = len(canonical_map)
    canonical_count = len(canonical_per_group)
    logger.info(
        f"Canonicalization: {raw_count:,} raw surface forms → "
        f"{canonical_count:,} canonical entities "
        f"({remapped:,} forms remapped, "
        f"compression ratio: {raw_count / max(canonical_count, 1):.2f}x)"
    )

    return canonical_map
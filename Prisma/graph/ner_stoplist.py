_NER_STOPWORDS: set[str] = {
    "acesta",
    "aceasta",
    "acești",
    "aceste",
    "acestuia",
    "acesteia",
    "acestora",
    "cel",
    "cea",
    "cei",
    "cele",
    "el",
    "ea",
    "ei",
    "ele",
    "noi",
    "lor",
    "lui",
    "său",
    "sa",
    "sine",
    "care",
    "cine",
    "unde",
    "cum",

    "reprezentanții",
    "reprezentantii",
    "oamenii",
    "bărbatul",
    "barbatul",
    "femeia",
    "copiii",
    "persoanele",

    "victima",
    "victimele",
    "suspectul",
    "suspectii",
    "suspecții",
    "inculpatul",
    "inculpații",
    "martorul",
    "martorii",
    "atacatorul",
    "atacatorii",
    "minorul",
    "minorii",
    "tinerii",
    "bătrânul",
    "vârstnicul",
    "locuitorii",
    "cetățenii",
    "alegătorii",
    "contribuabilii",
    "pensionarii",
    "elevii",
    "studenții",
    "pacienții",
    "angajații",

    "as-editor",
    "editor",
    "redacția",
    "redactia",
    "direcția marketing",
    "directia marketing",
    "comunicat de presă",
    "comunicat",
    "sursa foto",
    "foto",
    "copyright",
    "toate drepturile rezervate",
    "invitație",
    "invitatie",
    "astrele",
    "horoscop",
    "vremea",
    "meteo",
}


def is_ner_stopword(entity_text: str, entity_label: str) -> bool:
    """
    Returns True if the entity should be filtered out as a false positive.

    Matching is case-insensitive on the full entity text.
    Single-word and multi-word stopwords are both handled.

    Does NOT filter wire services — that is handled in graph_builder.py
    so the filter can be changed without re-running NER.
    """
    normalized = entity_text.strip().lower()

    if normalized in _NER_STOPWORDS:
        return True
    if '.ro' in normalized or '.com' in normalized or '.net' in normalized:
        return True

    return False

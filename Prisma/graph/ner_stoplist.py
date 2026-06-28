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

    "fanatik.ro",
    "digi24.ro",
    "hotnews.ro",
    "antena3.ro",
    "mediafax.ro",
}


def is_ner_stopword(entity_text: str, entity_label: str) -> bool:
    """
    Returns True if the entity should be filtered out as a false positive.

    Checks:
    1. Exact match against _NER_STOPWORDS (case-insensitive)
    2. Domain name pattern (.ro, .com, .net suffixes)
    """
    normalized = entity_text.strip().lower()

    if normalized in _NER_STOPWORDS:
        return True

    if any(normalized.endswith(tld) for tld in ('.ro', '.com', '.net', '.org', '.eu')):
        return True

    return False
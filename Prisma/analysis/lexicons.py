import re

_DIACRITICS_TABLE = str.maketrans(
    'șțăîâŞŢĂÎÂşţ',
    'staiaSTAIAst',
)

def normalise(text: str) -> str:
    return text.translate(_DIACRITICS_TABLE).lower()


# ── SENSATIONALISM: Title-level stylistic signals ─────────────────────────────

SENSATIONALIST_TIER1 = {
    # Tabloid amplifiers — unambiguously editorial exaggeration
    'soc', 'bomba', 'exclusiv', 'scandal', 'monstru', 'incredibil',
    'infiorator', 'halucinant', 'devastator', 'terifiant', 'cutremurator',
    'stupefiant', 'nebunie', 'groaznic', 'catastrofal', 'rusinos',
    'uluit', 'fenomenal', 'tulburator', 'revoltator', 'uluitor',
    'exploziv', 'bombastic', 'sfasietor',
    # Urgency / breaking markers — used almost exclusively for clickbait in RO press
    'breaking', 'de ultima ora',
}

SENSATIONALIST_TIER2 = {
    # Clickbait triggers — common in legitimate context too
    'iata', 'secretul', 'motivul pentru care', 'ce nu stiai',
    'asta e', 'nimeni nu', 'toata lumea', 'nu o sa crezi',
    'adevarul despre', 'cum e posibil', 'ce se intampla',
    'uite ce', 'nu ai ghici', 'ce a patit',
    # Emotional / dramatic — appear in straight news reporting as well
    'dramatic', 'colosal', 'emotionant', 'impresionant', 'miracol',
    'urgent', 'alerta', 'ultima ora',
}

QUOTE_OPEN  = re.compile(r'[„«]')
QUOTE_CLOSE = re.compile(r'[»"]')   


# ── CITATION QUALITY: Source attribution signals ──────────────────────────────

ATTRIBUTION_MARKERS = [
    # Direct speech attribution
    'potrivit', 'conform', 'a declarat', 'a anuntat', 'a spus',
    'a afirmat', 'a precizat', 'a subliniat', 'a punctat',
    'a adaugat', 'a completat', 'a confirmat', 'a dezvaluit',
    'a recunoscut', 'a reamintit', 'a explicat', 'a transmis',
    'a comunicat', 'a sustinut', 'a aratat', 'a indicat',
    'a mentionat', 'a remarcat',
    # Institutional / documentary citation
    'citat de', 'dupa cum', 'mentioneaza', 'reiese din',
    'potrivit datelor', 'conform statisticilor', 'conform raportului',
    'in declaratia', 'intr-un comunicat', 'printr-un comunicat',
    'conform documentului', 'conform studiului',
]

VAGUE_SOURCE_MARKERS = [
    # Unnamed sources — penalise when no named entity accompanies them
    'surse din', 'persoane din', 'cercuri apropiate',
    'oficiali care', 'persoane care', 'surse diplomatice',
    'surse judiciare', 'surse politice', 'surse apropiate',
    'din mediul politic', 'din mediul de afaceri',
    # Unverifiable
    'se vehiculeaza', 'informatii neconfirmate',
    'ar fi vorba', 'neconfirmat', 'informatii neoficiale',
    'din cate se stie', 'conform unor surse neoficiale',
]

SPECULATION_MARKERS = [
    # Conditional / speculative language
    'se zvoneste', 'ar fi', 's-ar parea', 'se pare ca',
    'se spune ca', 'ar putea fi', 'ar urma sa', 'neoficial',
    'se presupune', 'e posibil ca',
    'nu se stie daca', 'ramane de vazut',
]
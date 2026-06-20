# ── SENSATIONALISM: Title-level stylistic signals ─────────────────────────────

SENSATIONALIST_KEYWORDS = {
    # Tabloid amplifiers
    'șoc', 'bombă', 'exclusiv', 'scandal', 'monstru', 'incredibil',
    'înfiorător', 'halucinant', 'devastator', 'colosal', 'dramatic',
    'terifiant', 'cutremurător', 'stupefiant', 'nebunie', 'groaznic',
    'catastrofal', 'rușinos', 'uluit', 'fenomenal', 'tulburător',
    'revoltător', 'uluitor', 'exploziv', 'bombastic',
    # Clickbait triggers
    'iată', 'secretul', 'motivul pentru care', 'ce nu știai',
    'asta e', 'nimeni nu', 'toată lumea', 'nu o să crezi',
    'adevărul despre', 'cum e posibil',
    # Urgency markers
    'urgent', 'alertă', 'breaking', 'ultima oră', 'de ultimă oră',
    # Emotional appeals
    'emoționant', 'sfâșietor', 'impresionant', 'miracol',
}


# ── CITATION QUALITY: Source attribution signals ──────────────────────────────

ATTRIBUTION_MARKERS = [
    # Direct attribution (journalist names a source)
    'potrivit', 'conform', 'a declarat', 'a anunțat', 'a spus',
    'a afirmat', 'a precizat', 'a subliniat', 'a punctat',
    'a adăugat', 'a completat', 'a confirmat', 'a dezvăluit',
    'a recunoscut', 'a reamintit', 'a explicat', 'a transmis',
    'a comunicat', 'a susținut',
    # Institutional citation
    'citat de', 'după cum', 'menționează', 'reiese din',
    'potrivit datelor', 'conform statisticilor', 'conform raportului',
    'în declarația', 'într-un comunicat', 'printr-un comunicat',
]

VAGUE_SOURCE_MARKERS = [
    # Unnamed sources
    'surse', 'surse din', 'persoane din', 'cercuri apropiate',
    'oficiali care', 'persoane care', 'surse diplomatice',
    'surse judiciare', 'surse politice', 'surse apropiate',
    # Unverifiable attributions
    'se vehiculează', 'zvonuri', 'informații neconfirmate',
    'ar fi vorba', 'neconfirmat', 'informații neoficiale',
    'din câte se știe',
]

SPECULATION_MARKERS = [
    # Conditional / speculative language
    'se zvonește', 'ar fi', 's-ar părea', 'se pare că',
    'se spune că', 'ar putea fi', 'ar urma să', 'neoficial',
    'posibil', 'probabil', 'se presupune', 'e posibil ca',
    'nu se știe dacă', 'rămâne de văzut',
]


# ── DISCOURSE REGISTERS: Political vocabulary detection ───────────────────────

DISCOURSE_REGISTERS = {
    'national_sovereignty': [
        # Vocabulary emphasising national independence and self-determination
        'suveranitate', 'suveranitate națională', 'independență',
        'autodeterminare', 'interes național', 'stat suveran',
        'identitate națională', 'demnitate națională',
        'interese străine', 'ingerință', 'amestec extern',
    ],

    'eu_integration': [
        # Vocabulary emphasising European cooperation and convergence
        'integrare europeană', 'valori europene', 'standarde europene',
        'convergență', 'parteneriat european', 'acquis comunitar',
        'comunitate europeană', 'solidaritate europeană',
        'proiect european', 'parcurs european',
    ],

    'eu_criticism': [
        # Vocabulary critical of EU institutions or policies
        'birocrați de la bruxelles', 'dictat european',
        'impunere', 'cedare suveranitate', 'federalizare',
        'pierderea suveranității', 'comisia impune',
    ],

    'institutional_trust': [
        # Vocabulary expressing confidence in state institutions
        'statul de drept', 'independența justiției',
        'instituții democratice', 'separația puterilor',
        'transparență', 'integritate', 'responsabilizare',
        'anticorupție', 'reformă instituțională',
    ],

    'institutional_criticism': [
        # Vocabulary critical of state institutions or judicial system
        'stat paralel', 'abuz', 'dosar politic',
        'persecuție politică', 'vânătoare de vrăjitoare',
        'anchetă fabricată', 'politizare', 'captură',
        'servicii secrete', 'stat profund', 'deep state',
    ],

    'traditional_identity': [
        # Vocabulary referencing cultural, religious, or ethnic identity
        'tradiție', 'ortodoxie', 'valori tradiționale',
        'credință', 'identitate culturală', 'moștenire',
        'neam', 'biserică', 'familie tradițională',
        'rădăcini', 'spiritualitate',
    ],

    'modernisation': [
        # Vocabulary emphasising progress and change
        'modernizare', 'reformă', 'digitalizare', 'inovație',
        'progres', 'dezvoltare durabilă', 'tranziție',
        'societate civilă', 'deschidere', 'incluziune',
        'diversitate',
    ],

    'crisis_alarm': [
        # Vocabulary invoking threat or emergency — used across all orientations
        'criză gravă', 'pericol iminent', 'amenințare existențială',
        'dezastru', 'colaps', 'catastrofă', 'situație critică',
        'stare de urgență', 'punct critic', 'alarmant',
        'îngrijorător', 'fără precedent',
    ],
}


# ── DERIVED: Combined rhetoric vocabulary for intensity scoring ───────────────

ALL_RHETORIC_TERMS = set()
for terms in DISCOURSE_REGISTERS.values():
    ALL_RHETORIC_TERMS.update(t.lower() for t in terms)
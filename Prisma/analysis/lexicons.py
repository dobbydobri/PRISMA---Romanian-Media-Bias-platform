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
    'adevărul despre', 'cum e posibil', 'de ce', 'ce se întâmplă',
    'uite ce', 'nu ai ghici', 'ce a pățit',
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
    'a comunicat', 'a susținut', 'a arătat', 'a indicat',
    'a menționat', 'a remarcat',
    # Institutional citation
    'citat de', 'după cum', 'menționează', 'reiese din',
    'potrivit datelor', 'conform statisticilor', 'conform raportului',
    'în declarația', 'într-un comunicat', 'printr-un comunicat',
    'conform documentului', 'conform studiului',
]

VAGUE_SOURCE_MARKERS = [
    # Unnamed sources
    'surse', 'surse din', 'persoane din', 'cercuri apropiate',
    'oficiali care', 'persoane care', 'surse diplomatice',
    'surse judiciare', 'surse politice', 'surse apropiate',
    'din mediul politic', 'din mediul de afaceri',
    # Unverifiable attributions
    'se vehiculează', 'zvonuri', 'informații neconfirmate',
    'ar fi vorba', 'neconfirmat', 'informații neoficiale',
    'din câte se știe', 'conform unor surse neoficiale',
]

SPECULATION_MARKERS = [
    # Conditional / speculative language
    'se zvonește', 'ar fi', 's-ar părea', 'se pare că',
    'se spune că', 'ar putea fi', 'ar urma să', 'neoficial',
    'posibil', 'probabil', 'se presupune', 'e posibil ca',
    'nu se știe dacă', 'rămâne de văzut',
]


# ── DISCOURSE REGISTERS: Political vocabulary detection ───────────────────────
#
# national_sovereignty removed — handled by transformer sovereignism axis (0.74 F1).
# eu_integration and eu_criticism expanded — these are now the primary NLP signal
# for EU orientation, replacing the dropped LLM/transformer eu_orientation axis.
# institutional_criticism serves as the anti-establishment proxy, replacing the
# dropped LLM/transformer anti_establishment axis.

DISCOURSE_REGISTERS = {
    'eu_integration': [
        # Vocabulary framing EU/Euro-Atlantic alignment positively
        'integrare europeană', 'valori europene', 'standarde europene',
        'convergență', 'parteneriat european', 'acquis comunitar',
        'comunitate europeană', 'solidaritate europeană',
        'proiect european', 'parcurs european',
        # Institutional references in positive framing context
        'familia europeană', 'angajament european', 'vocație europeană',
        'construcție europeană', 'coeziune europeană',
        # Specific EU milestones and frameworks
        'aderare la zona euro', 'absorbția fondurilor',
        'spațiul schengen', 'mecanismul de cooperare și verificare',
        # Euro-Atlantic dimension
        'parteneriat transatlantic', 'alianța nato',
        'angajament nato', 'flancul estic',
    ],

    'eu_criticism': [
        # Vocabulary framing EU institutions or policies critically
        'birocrați de la bruxelles', 'dictat european',
        'cedare suveranitate', 'federalizare',
        'pierderea suveranității',
        # Critical framing of EU relationship 
        'periferia europei', 'colonie europeană',
        'reglementare excesivă', 'birocrație europeană',
        'interferență europeană', 'control european',
        # Sovereignty loss framing
        'bruxelles-ul decide', 'impus de bruxelles',
    ],

    'institutional_trust': [
        # Vocabulary expressing confidence in state institutions
        'statul de drept', 'independența justiției',
        'instituții democratice', 'separația puterilor',
        'integritate', 'responsabilizare',
        'anticorupție', 'reformă instituțională',
        'proces echitabil', 'prezumția de nevinovăție',
        'controlul constituționalității', 'mecanisme de control',
        'răspundere publică',
    ],

    'institutional_criticism': [
        # Vocabulary critical of state institutions — anti-establishment proxy
        'stat paralel', 'abuz instituțional', 'dosar politic',
        'persecuție politică', 'vânătoare de vrăjitoare',
        'anchetă fabricată', 'politizare', 'captură instituțională',
        'servicii secrete', 'stat profund', 'deep state',
        # Judicial system distrust
        'justiție selectivă', 'procuror instrumentalizat',
        'protocoale secrete', 'interceptări ilegale',
        'decizie politică', 'condamnare politică',
        # Intelligence services framing
        'statul securist', 'moștenirea securității',
        'ofițeri acoperiți', 'influența serviciilor',
    ],

    'traditional_identity': [
        # Vocabulary referencing cultural, religious, or ethnic identity
        'tradiție', 'ortodoxie', 'valori tradiționale',
        'credință', 'identitate culturală', 'moștenire',
        'neam', 'biserică', 'familie tradițională',
        'rădăcini', 'spiritualitate',
        'patrimoniu', 'obiceiuri', 'strămoși',
    ],

    'modernisation': [
        # Vocabulary emphasising progress and societal change
        'modernizare', 'reformă', 'digitalizare', 'inovație',
        'progres', 'dezvoltare durabilă', 'tranziție',
        'societate civilă', 'deschidere', 'incluziune',
        'diversitate', 'transformare digitală',
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
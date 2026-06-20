FORBIDDEN_TITLES = {'editor', 'autor', 'reporter', 'foto', 'sursa', 'corespondent', 'agerpres', 'redactia'}

def extract_entities(texts: list[str], nlp, spacy_batch_size: int = 8) -> list[list[tuple]]:
    VALID_LABELS = {'PERSON', 'ORGANIZATION', 'GPE', 'LOC', 'EVENT'}
    CONTEXT_STOPWORDS = {'foto', 'autor', 'sursa', 'imagine', 'credit', 'reporter', 'redactor', 'corespondent'}
    JOURNALISTIC_NOISE = {'INTERVIU', 'EXCLUSIV', 'FOTO', 'UPDATE', 'VIDEO', 'DOCUMENT', 'LIVE', 'BREAKING'}
    
    ORG_BLOCKLIST = {
        'facebook', 'instagram', 'telegram', 'twitter', 'tiktok', 'whatsapp', 'youtube',
        'inquam', 'agerpres', 'getty', 'reuters', 'mediafax', 'cnn', 'cnbc', 'afp',
        'antena', 'digi', 'b1', 'protv', 'realitatea', 'guardian', 'bbc', 'ap', 'bloomberg',
        'trunchiat', 'fals', 'context lipsă', 'fake news', 'erata', 'google', 'spotmedia', 'ziare.com', 'tik tok', 'covid', 'dreamstime', 'foto'
    }

    results = []
    for doc in nlp.pipe(texts, batch_size=spacy_batch_size):
        entities = []
        for ent in doc.ents:
            text_clean = ent.text.strip()

            if ent.label_ not in VALID_LABELS:
                continue
            if not text_clean or not text_clean[0].isupper():
                continue
            if '/' in text_clean or len(text_clean) > 40:
                continue
            if text_clean.upper() in JOURNALISTIC_NOISE:
                continue

            if ent.label_ == 'PERSON':
                window_start = max(0, ent.start - 3)
                context_window = doc[window_start : ent.start]
                is_media_credit = any(''.join(c for c in token.text.lower() if c.isalpha()) in CONTEXT_STOPWORDS for token in context_window)
                if is_media_credit:
                    continue

            if ent.label_ == 'ORGANIZATION':
                if any(blocked in text_clean.lower() for blocked in ORG_BLOCKLIST):
                    continue

            if ent.label_ == 'LOC':
                if len(text_clean.split()) > 5 or text_clean.lower() in ('tik tok', 'tiktok'):
                    continue    

            entities.append((text_clean, ent.label_))

        # Deduplicate within the same article
        seen = set()
        unique = [e for e in entities if e[0] not in seen and not seen.add(e[0])]
        results.append(unique)
        
    return results

def filter_author_entities(entities: list[tuple], article_authors: list[str] | None, global_blocklist: set[str]) -> list[tuple]:
    """Filters extracted entities against the dynamic blocklist."""
    if not entities:
        return entities

    local_names = {a.lower().strip() for a in (article_authors or []) if a}
    all_known = local_names | global_blocklist

    filtered = []
    for entity_text, entity_label in entities:
        if entity_label != 'PERSON':
            filtered.append((entity_text, entity_label))
            continue

        entity_lower = entity_text.lower().strip()
        entity_words = set(entity_lower.split())

        is_journalist = False
        
        for known in all_known:
            known_words = set(known.split())
            if entity_lower in known or known in entity_lower:
                is_journalist = True
                break
            if len(entity_words & known_words) >= 2:
                is_journalist = True
                break
                
        if not is_journalist and any(title in entity_lower for title in FORBIDDEN_TITLES):
            is_journalist = True

        if not is_journalist:
            filtered.append((entity_text, entity_label))

    return filtered
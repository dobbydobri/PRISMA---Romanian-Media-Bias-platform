import os
import sys
import time
import logging
import psycopg2
from psycopg2.extras import execute_values
import spacy
from pathlib import Path

from shared.ner_utils import filter_author_entities
from entity_normalizer import normalize_unicode, normalize_entity
from ner_stoplist import is_ner_stopword

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise EnvironmentError("DATABASE_URL not set")

DB_BATCH_SIZE = int(os.getenv("NER_BATCH_SIZE", "200"))
SPACY_BATCH_SIZE = int(os.getenv("NER_SPACY_BATCH", "4"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

VALID_LABELS = {'PERSON', 'ORGANIZATION', 'GPE', 'LOC', 'EVENT'}
CONTEXT_STOPWORDS = {'foto', 'autor', 'sursa', 'imagine', 'credit', 'reporter', 'redactor', 'corespondent'}
JOURNALISTIC_NOISE = {'INTERVIU', 'EXCLUSIV', 'FOTO', 'UPDATE', 'VIDEO', 'DOCUMENT', 'LIVE', 'BREAKING'}
ORG_BLOCKLIST = {
    'facebook', 'instagram', 'telegram', 'twitter', 'tiktok', 'whatsapp', 'youtube',
    'inquam', 'getty', 'cnn', 'cnbc', 'antena', 'digi', 'b1', 'protv', 'realitatea',
    'guardian', 'bbc', 'bloomberg', 'trunchiat', 'fals', 'context lipsă', 'fake news',
    'erata', 'google', 'spotmedia', 'ziare.com', 'tik tok', 'covid', 'dreamstime', 'foto',
}


def extract_entity_lemma(ent) -> str:
    """
    Extract the lemmatized canonical form of a spaCy entity span.

    Uses token-level lemmas from ro_core_news_lg's trainable lemmatizer.
    Preserves the capitalization pattern from the surface form per token,
    since the lemmatizer sometimes lowercases proper nouns.

    Three capitalization cases handled per token:
    - ALL CAPS (len > 1): keep uppercase  (NATO → NATO, not Nato)
    - Title Case surface: capitalize lemma (România → România, not românia)
    - Lowercase: keep as-is
    """
    lemma_tokens = [token.lemma_ for token in ent]
    surface_tokens = ent.text.split()

    recased = []
    for i, lt in enumerate(lemma_tokens):
        if i < len(surface_tokens):
            st = surface_tokens[i]
            if st.isupper() and len(st) > 1:
                lt = lt.upper()                        # NATO → NATO
            elif st[0].isupper() and lt[0].islower():
                lt = lt[0].upper() + lt[1:]            # România → România
        recased.append(lt)

    lemma = ' '.join(recased).strip()
    return normalize_unicode(lemma)


def extract_entities_with_lemmas(texts: list[str], nlp, spacy_batch_size: int = 8) -> list[list[tuple]]:
    """
    Run spaCy NER on a batch of article texts and return per-article lists of
    (surface_text, lemma, label) triples.

    Applies the same basic quality filters as the previous extract_entities()
    helper (label allowlist, capitalization check, length limit, context window,
    org blocklist, journalistic noise). The NER stoplist and author filter are
    applied downstream in main(), not here, to keep this function pure.
    """
    results = []
    for doc in nlp.pipe(texts, batch_size=spacy_batch_size):
        entities = []
        for ent in doc.ents:
            surface = ent.text.strip()

            if ent.label_ not in VALID_LABELS:
                continue
            if not surface or not surface[0].isupper():
                continue
            if '/' in surface or len(surface) > 40:
                continue
            if surface.upper() in JOURNALISTIC_NOISE:
                continue
            if any(surface.upper().startswith(noise + ' ') for noise in JOURNALISTIC_NOISE):
                continue
            if '*' in surface or surface.count('-') > 1:
                continue

            if ent.label_ == 'PERSON':
                window_start = max(0, ent.start - 3)
                context_window = doc[window_start:ent.start]
                is_media_credit = any(
                    ''.join(c for c in token.text.lower() if c.isalpha()) in CONTEXT_STOPWORDS
                    for token in context_window
                )
                if is_media_credit:
                    continue

            if ent.label_ == 'ORGANIZATION':
                if any(blocked in surface.lower() for blocked in ORG_BLOCKLIST):
                    continue

            if ent.label_ == 'LOC':
                if len(surface.split()) > 5 or surface.lower() in ('tik tok', 'tiktok'):
                    continue

            lemma = extract_entity_lemma(ent)
            entities.append((surface, lemma, ent.label_))

        results.append(entities)

    return results


def normalize_article_entities(
    raw_entities: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    """
    Two-pass normalization for a single article's entity list.

    Pass 1 (passes 0-4): normalize each entity without article context.
    Pass 2 (pass 5): surname merge using the pre-normalized list as context.

    Returns a deduplicated list of (normalized_text, label) pairs.
    The deduplication key is the normalized canonical form, not the raw surface.
    """
    # Pass 1: normalize without surname context (passes 0-4)
    pre_normalized: list[tuple[str, str]] = []
    for surface, lemma, label in raw_entities:
        canonical = normalize_entity(surface, label=label, lemma=lemma, article_entities=None)
        if canonical:
            pre_normalized.append((canonical, label))

    # Pass 2: surname merge with article context (pass 5)
    final_entities: list[tuple[str, str]] = []
    for canonical, label in pre_normalized:
        merged = normalize_entity(canonical, label=label, lemma=None, article_entities=pre_normalized)
        if merged:
            final_entities.append((merged, label))

    # Deduplicate on normalized canonical form (preserving first occurrence)
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for text, label in final_entities:
        key = text.lower()
        if key not in seen:
            seen.add(key)
            unique.append((text, label))

    return unique


def build_journalist_blocklist_sync(conn) -> set[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT UNNEST(authors) FROM articles WHERE authors IS NOT NULL AND authors != '{}'")
    blocklist = {row[0].lower().strip() for row in cursor.fetchall() if row[0]}
    logger.info(f"Journalist blocklist built: {len(blocklist):,} names.")
    cursor.close()
    return blocklist


def main():
    try:
        conn = psycopg2.connect(DB_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)

    logger.info("Initializing GPU and loading spaCy Romanian model...")
    try:
        spacy.require_gpu()
        nlp = spacy.load("ro_core_news_lg")
        logger.info("spaCy successfully loaded onto the GPU!")
    except OSError as e:
        logger.error(f"Spacy model not found: {e}. Ensure it's installed in the Docker image.")
        sys.exit(1)
    except Exception as e:
        logger.warning(f"Could not initialize GPU for spaCy: {e}. Falling back to CPU.")
        nlp = spacy.load("ro_core_news_lg")

    journalist_blocklist = build_journalist_blocklist_sync(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(article_id), 0) FROM article_entities_full;")
    last_id = cursor.fetchone()[0]
    logger.info(f"Resuming from Article ID: {last_id}")
    logger.info(f"Batch config: DB_BATCH_SIZE={DB_BATCH_SIZE}, SPACY_BATCH_SIZE={SPACY_BATCH_SIZE}")

    total_processed = 0

    while True:
        batch_start = time.time()

        try:
            cursor.execute("""
                SELECT id, content_text, authors FROM articles
                WHERE id > %s AND content_text IS NOT NULL
                ORDER BY id ASC LIMIT %s;
            """, (last_id, DB_BATCH_SIZE))

            batch = cursor.fetchall()
            if not batch:
                logger.info("Caught up to present day. Idling for new articles...")
                time.sleep(60)
                continue

            ids = [row[0] for row in batch]
            authors_list = [row[2] for row in batch]

            texts = [normalize_unicode(row[1]) for row in batch]

            avg_chars = sum(len(t) for t in texts) / len(texts)
            logger.info(f"Batch of {len(batch)} articles | avg length: {avg_chars:,.0f} chars")

            raw_entity_batches = extract_entities_with_lemmas(
                texts, nlp=nlp, spacy_batch_size=SPACY_BATCH_SIZE
            )

            insert_data = []
            for a_id, raw_entities, authors in zip(ids, raw_entity_batches, authors_list):

                after_stoplist = [
                    (surface, lemma, label)
                    for surface, lemma, label in raw_entities
                    if not is_ner_stopword(surface, label)
                ]

                pairs_for_author_filter = [(s, lb) for s, _l, lb in after_stoplist]
                filtered_pairs = filter_author_entities(pairs_for_author_filter, authors, journalist_blocklist)
                filtered_set = {text for text, _ in filtered_pairs}

                after_author_filter = [
                    (surface, lemma, label)
                    for surface, lemma, label in after_stoplist
                    if surface in filtered_set
                ]

                normalized = normalize_article_entities(after_author_filter)

                for norm_text, label in normalized:
                    insert_data.append((a_id, norm_text, label))

            if insert_data:
                execute_values(cursor, """
                    INSERT INTO article_entities_full (article_id, entity_text, entity_label)
                    VALUES %s ON CONFLICT (article_id, entity_text, entity_label) DO NOTHING
                """, insert_data)

            conn.commit()

            last_id = ids[-1]
            total_processed += len(batch)
            elapsed = time.time() - batch_start
            logger.info(
                f"[Total: {total_processed:,}] Batch done in {elapsed:.1f}s "
                f"({len(batch)/elapsed:.1f} articles/s) | Last ID: {last_id}"
            )

        except psycopg2.OperationalError as e:
            logger.error(f"Database connection lost: {e}. Reconnecting in 5s...")
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(5)
            try:
                conn = psycopg2.connect(DB_URL)
                cursor = conn.cursor()
                logger.info(f"Reconnected. Resuming from Article ID: {last_id}")
            except Exception as reconnect_err:
                logger.error(f"Reconnection failed: {reconnect_err}. Retrying...")
                continue

        except MemoryError:
            logger.error(
                f"MemoryError on batch near Article ID {last_id}. "
                f"Consider lowering NER_SPACY_BATCH (currently {SPACY_BATCH_SIZE}). "
                f"Sleeping 10s before retry..."
            )
            try:
                conn.rollback()
            except Exception:
                pass
            time.sleep(10)

        except Exception as e:
            logger.error(f"Batch processing failed: {e}. Resuming from Article ID: {last_id}")
            try:
                conn.rollback()
            except Exception:
                pass
            time.sleep(2)

    try:
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
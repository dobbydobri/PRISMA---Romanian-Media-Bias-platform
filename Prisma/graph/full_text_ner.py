import os
import sys
import time
import logging
import psycopg2
from psycopg2.extras import execute_values
import stanza

from shared.ner_utils import filter_author_entities
from entity_normalizer import normalize_unicode, normalize_entity
from ner_stoplist import is_ner_stopword

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise EnvironmentError("DATABASE_URL not set")

DB_BATCH_SIZE = int(os.getenv("NER_BATCH_SIZE", "100"))
NER_BATCH_SIZE = int(os.getenv("NER_MODEL_BATCH", "8"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

_LABEL_MAP: dict[str, str] = {
    "PERSON":       "PERSON",
    "ORG":          "ORGANIZATION",
    "GPE":          "GPE",
    "LOC":          "LOC",
    "EVENT":        "EVENT",
    "NAT_REL_POL":  "ORGANIZATION",  
    "FACILITY":     "LOC",           
}

ORG_BLOCKLIST: frozenset[str] = frozenset({
    'facebook', 'instagram', 'telegram', 'twitter', 'tiktok', 'whatsapp',
    'youtube', 'inquam', 'getty', 'cnn', 'cnbc', 'antena', 'digi', 'b1',
    'protv', 'realitatea', 'guardian', 'bbc', 'bloomberg', 'trunchiat',
    'fals', 'context lipsă', 'fake news', 'erata', 'google', 'spotmedia',
    'ziare.com', 'tik tok', 'covid', 'dreamstime', 'foto',
})

JOURNALISTIC_NOISE: frozenset[str] = frozenset({
    'INTERVIU', 'EXCLUSIV', 'FOTO', 'UPDATE', 'VIDEO',
    'DOCUMENT', 'LIVE', 'BREAKING',
})


def load_roner_model(use_gpu: bool = True) -> 'roner.NER':
    import roner
    model = roner.NER(
        use_gpu=use_gpu,
        batch_size=NER_BATCH_SIZE,
        named_persons_only=True,  
    )
    logger.info(
        f"RoNER loaded (use_gpu={use_gpu}, batch_size={NER_BATCH_SIZE}, "
        f"named_persons_only=True)"
    )
    return model


def extract_entities_roner(
    texts: list[str],
    model,
) -> list[list[tuple[str, str]]]:
    results = []

    try:
        roner_outputs = model(texts)
    except Exception as e:
        logger.error(f"RoNER inference failed: {e}")
        return [[] for _ in texts]

    for output in roner_outputs:
        entities: list[tuple[str, str]] = []
        current_text: list[str] = []
        current_label: str | None = None

        for word in output['words']:
            tag = word['tag']

            if tag.startswith('B-'):
                # Flush any in-progress entity
                if current_text and current_label:
                    entity_text = ' '.join(current_text).strip()
                    mapped = _LABEL_MAP.get(current_label)
                    if mapped:
                        entities.append((entity_text, mapped))
                current_text = [word['text']]
                current_label = tag[2:]  # "B-PERSON" → "PERSON"

            elif tag.startswith('I-') and current_label == tag[2:]:
                # Continuation of current entity
                current_text.append(word['text'])

            else:
                # O tag or label mismatch — flush current entity
                if current_text and current_label:
                    entity_text = ' '.join(current_text).strip()
                    mapped = _LABEL_MAP.get(current_label)
                    if mapped:
                        entities.append((entity_text, mapped))
                current_text = []
                current_label = None

        # Flush final entity
        if current_text and current_label:
            entity_text = ' '.join(current_text).strip()
            mapped = _LABEL_MAP.get(current_label)
            if mapped:
                entities.append((entity_text, mapped))

        # Basic quality filters (model-agnostic, same intent as spaCy version)
        filtered: list[tuple[str, str]] = []
        for surface, label in entities:
            # Must start with uppercase (proper noun sanity check)
            if not surface or not surface[0].isupper():
                continue

            # Length limits: skip empty or suspiciously long spans
            if len(surface) > 60:
                continue

            # Journalistic noise prefix: "VIDEO Donald Trump" etc.
            surface_upper = surface.upper()
            if surface_upper in JOURNALISTIC_NOISE:
                continue
            if any(surface_upper.startswith(noise + ' ') for noise in JOURNALISTIC_NOISE):
                continue

            # Skip entities with special characters indicating artifacts
            if '*' in surface:
                continue

            # Organization blocklist
            if label == 'ORGANIZATION':
                if any(blocked in surface.lower() for blocked in ORG_BLOCKLIST):
                    continue

            # LOC: reject implausibly long location spans
            if label == 'LOC' and len(surface.split()) > 6:
                continue

            filtered.append((surface, label))

        results.append(filtered)

    return results


def lemmatize_entities(
    entities: list[tuple[str, str]],
    stanza_pipeline,
) -> list[tuple[str, str, str]]:
    if not entities:
        return []

    results: list[tuple[str, str, str]] = []

    for surface, label in entities:
        try:
            doc = stanza_pipeline(surface)
            lemma_tokens = []
            surface_tokens = surface.split()

            all_words = [w for sent in doc.sentences for w in sent.words]

            for i, word in enumerate(all_words):
                lt = word.lemma or word.text
                # Re-apply capitalization from surface form
                if i < len(surface_tokens):
                    st = surface_tokens[i]
                    if st.isupper() and len(st) > 1:
                        lt = lt.upper()           # NATO → NATO
                    elif st and st[0].isupper() and lt and lt[0].islower():
                        lt = lt[0].upper() + lt[1:]  # România → România
                lemma_tokens.append(lt)

            lemma = ' '.join(lemma_tokens).strip()
            lemma = normalize_unicode(lemma)

        except Exception:
            # If lemmatization fails for any entity, use surface form as lemma
            lemma = surface

        results.append((surface, lemma, label))

    return results


def normalize_article_entities(
    raw_entities: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    pre_normalized: list[tuple[str, str]] = []
    for surface, lemma, label in raw_entities:
        canonical = normalize_entity(surface, label=label, lemma=lemma, article_entities=None)
        if canonical:
            pre_normalized.append((canonical, label))

    final_entities: list[tuple[str, str]] = []
    for canonical, label in pre_normalized:
        merged = normalize_entity(canonical, label=label, lemma=None, article_entities=pre_normalized)
        if merged:
            final_entities.append((merged, label))

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
    cursor.execute(
        "SELECT DISTINCT UNNEST(authors) FROM articles "
        "WHERE authors IS NOT NULL AND authors != '{}'"
    )
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

    logger.info("Loading RoNER (bert-base-romanian-ner)...")
    use_gpu = True
    try:
        import torch
        use_gpu = torch.cuda.is_available()
        if use_gpu:
            logger.info("CUDA available — RoNER will use GPU.")
        else:
            logger.warning("CUDA not available — RoNER will use CPU (slower).")
    except ImportError:
        use_gpu = False

    try:
        model = load_roner_model(use_gpu=use_gpu)
    except Exception as e:
        logger.error(f"Failed to load RoNER: {e}")
        sys.exit(1)

    logger.info("Loading Stanza Romanian lemmatizer...")
    try:
        stanza.download('ro', processors='tokenize,lemma', verbose=False)
        stanza_pipeline = stanza.Pipeline(
            'ro',
            processors='tokenize,lemma',
            use_gpu=use_gpu,
            verbose=False,
        )
        logger.info("Stanza lemmatizer loaded.")
    except Exception as e:
        logger.error(f"Failed to load Stanza lemmatizer: {e}")
        sys.exit(1)

    journalist_blocklist = build_journalist_blocklist_sync(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(article_id), 0) FROM article_entities_full;")
    last_id = cursor.fetchone()[0]
    logger.info(f"Resuming from Article ID: {last_id}")
    logger.info(
        f"Batch config: DB_BATCH_SIZE={DB_BATCH_SIZE}, "
        f"NER_MODEL_BATCH={NER_BATCH_SIZE}"
    )

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

            ids         = [row[0] for row in batch]
            authors_list = [row[2] for row in batch]

            texts = [normalize_unicode(row[1]) for row in batch]

            avg_chars = sum(len(t) for t in texts) / len(texts)
            logger.info(f"Batch of {len(batch)} articles | avg length: {avg_chars:,.0f} chars")

            # Step 1: RoNER entity extraction
            raw_entity_batches = extract_entities_roner(texts, model)

            insert_data = []
            for a_id, raw_entities, authors in zip(ids, raw_entity_batches, authors_list):

                # Step 2: NER stoplist filter (safety net — named_persons_only
                after_stoplist = [
                    (surface, label)
                    for surface, label in raw_entities
                    if not is_ner_stopword(surface, label)
                ]

                # Step 3: Journalist/author blocklist filter
                filtered_pairs = filter_author_entities(
                    after_stoplist, authors, journalist_blocklist
                )

                # Step 4: Stanza lemmatization for inflection resolution
                with_lemmas = lemmatize_entities(filtered_pairs, stanza_pipeline)

                # Step 5: Two-pass normalization n
                normalized = normalize_article_entities(with_lemmas)

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
                f"MemoryError near Article ID {last_id}. "
                f"Lower NER_MODEL_BATCH (currently {NER_BATCH_SIZE}). "
                f"Sleeping 10s..."
            )
            try:
                conn.rollback()
            except Exception:
                pass
            time.sleep(10)

        except Exception as e:
            logger.error(
                f"Batch processing failed near Article ID {last_id}: {e}"
            )
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
import asyncio
import asyncpg
import os
import time
import logging
import spacy
from concurrent.futures import ThreadPoolExecutor
from sentence_transformers import SentenceTransformer

# Shared NER utilities — mounted at /app/shared inside Docker
from shared.ner_utils import extract_entities, filter_author_entities

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DB_URL            = os.getenv("DATABASE_URL")
if not DB_URL:
    raise EnvironmentError("DATABASE_URL not set")
BATCH_SIZE        = 64
MAX_WAIT_TIME     = 5.0
MODEL_NAME        = 'intfloat/multilingual-e5-large'
EMBEDDING_VERSION = 'v2_entity_augmented'
MAX_CONTENT_CHARS = 1500

live_queue     = asyncio.Queue()
model          = None
nlp            = None
listener_ready = asyncio.Event()

journalist_blocklist: set[str] = set()

_ner_executor   = ThreadPoolExecutor(max_workers=1)
_embed_executor = ThreadPoolExecutor(max_workers=1)


# ── Dynamic Journalist Blocklist ───────────────────────────────────────────────

async def build_journalist_blocklist(pool) -> set[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT UNNEST(authors) AS name
            FROM articles
            WHERE authors IS NOT NULL AND authors != '{}'
        """)
    blocklist = {row['name'].lower().strip() for row in rows if row['name']}
    logger.info(f"Journalist blocklist built: {len(blocklist)} known names automatically protected.")
    return blocklist


# ── NER (delegated to shared ner_utils) ───────────────────────────────────────

async def run_ner_batch(texts: list[str]) -> list[list[tuple]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _ner_executor,
        extract_entities,
        texts,
        nlp,   
        32    
    )


# ── Text construction ──────────────────────────────────────────────────────────

def build_augmented_text(title: str, content: str, entities: list[tuple]) -> str:
    if not entities:
        return f"passage: {title} {(content or '')[:MAX_CONTENT_CHARS]}"

    persons = [e[0] for e in entities if e[1] == 'PERSON'][:6]
    orgs    = [e[0] for e in entities if e[1] == 'ORGANIZATION'][:4]
    locs    = [e[0] for e in entities if e[1] in ('GPE', 'LOC')][:4]
    events  = [e[0] for e in entities if e[1] == 'EVENT'][:2]

    parts = []
    if persons: parts.append(f"Persoane: {', '.join(persons)}")
    if orgs:    parts.append(f"Organizații: {', '.join(orgs)}")
    if locs:    parts.append(f"Locuri: {', '.join(locs)}")
    if events:  parts.append(f"Evenimente: {', '.join(events)}")

    entity_prefix = ". ".join(parts)
    return f"passage: {entity_prefix}. {title} {(content or '')[:MAX_CONTENT_CHARS]}"


# ── Encoding ───────────────────────────────────────────────────────────────────

def _encode(texts: list[str]) -> list:
    return model.encode(texts, normalize_embeddings=True).tolist()

async def run_encoding(texts: list[str]) -> list:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embed_executor, _encode, texts)


# ── Core pipeline ──────────────────────────────────────────────────────────────

async def embed_and_update(pool, records):
    if not records:
        return

    ids          = [r['id'] for r in records]
    titles       = [r['title'] or '' for r in records]
    contents     = [r['content_text'] or '' for r in records]
    authors_list = [r.get('authors', []) for r in records]

    # 1. Run NER on title + first 500 chars of content (preview pass)
    raw_texts_for_ner  = [f"{t} {c[:500]}" for t, c in zip(titles, contents)]
    raw_entity_batches = await run_ner_batch(raw_texts_for_ner)

    # 2. Filter journalists — pass the global blocklist explicitly
    entity_batches = [
        filter_author_entities(ents, auths, journalist_blocklist)
        for ents, auths in zip(raw_entity_batches, authors_list)
    ]

    # 3. Save entities to article_entities table
    entity_rows = [
        (article_id, entity_text, entity_label)
        for article_id, entities in zip(ids, entity_batches)
        for entity_text, entity_label in entities
    ]

    if entity_rows:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO article_entities (article_id, entity_text, entity_label)
                VALUES ($1, $2, $3)
                ON CONFLICT (article_id, entity_text, entity_label) DO NOTHING
                """,
                entity_rows
            )

    # 4. Build entity-augmented texts for the embedding model
    augmented_texts = [
        build_augmented_text(title, content, entities)
        for title, content, entities in zip(titles, contents, entity_batches)
    ]

    # 5. Encode on GPU (non-blocking via executor)
    start          = time.time()
    embeddings_list = await run_encoding(augmented_texts)

    # 6. Write embeddings back to articles table
    str_embeddings = ['[' + ','.join(map(str, emb)) + ']' for emb in embeddings_list]

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            UPDATE articles
            SET embedding         = $1::vector,
                embedded_at       = NOW(),
                embedding_model   = $2,
                embedding_version = $3
            WHERE id = $4
            """,
            list(zip(
                str_embeddings,
                [MODEL_NAME] * len(ids),
                [EMBEDDING_VERSION] * len(ids),
                ids
            ))
        )

    logger.info(f"Embedded {len(ids)} articles with entity augmentation in {time.time()-start:.2f}s")


# ── Startup sweep ──────────────────────────────────────────────────────────────

async def run_startup_sweep(pool):
    """Backfill: processes any article not yet on embedding_version v2."""
    logger.info("Starting backfill sweep (v2 entity-augmented)...")
    total = 0
    while True:
        async with pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT id, title, content_text, authors
                FROM articles
                WHERE embedding_version != $1 OR embedding IS NULL
                ORDER BY id
                LIMIT $2
                """,
                EMBEDDING_VERSION, BATCH_SIZE
            )
        if not records:
            logger.info(f"Backfill complete. Total: {total}")
            break
        await embed_and_update(pool, records)
        total += len(records)
        logger.info(f"[BACKFILL] {total} articles processed")


# ── Live listeners and processors ─────────────────────────────────────────────

async def handle_new_article(connection, pid, channel, payload):
    logger.info(f"[NOTIFY] Received article_id={payload}")
    await live_queue.put(int(payload))


async def maintain_listener():
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(DB_URL)
            await conn.add_listener('new_article', handle_new_article)
            listener_ready.set()
            logger.info("LISTEN connection established and active.")
            while not conn.is_closed():
                await asyncio.sleep(5)
            raise ConnectionError("Connection closed by server.")
        except Exception as e:
            logger.warning(f"LISTEN connection lost: {e}. Reconnecting in 5s...")
            if conn and not conn.is_closed():
                await conn.close()
            await asyncio.sleep(5)


async def periodic_catchup(pool):
    logger.info("Periodic catch-up daemon started.")
    while True:
        await asyncio.sleep(30)
        async with pool.acquire() as conn:
            missed = await conn.fetch(
                """
                SELECT id FROM articles
                WHERE embedding IS NULL
                ORDER BY id LIMIT $1
                """,
                BATCH_SIZE * 2
            )
        if missed:
            for row in missed:
                await live_queue.put(row['id'])
            logger.info(f"[CATCHUP] Re-queued {len(missed)} missed articles.")


async def live_batch_processor(pool):
    logger.info("Entering live batch processing loop.")
    while True:
        try:
            batch_ids  = []
            first_id   = await live_queue.get()
            batch_ids.append(first_id)

            start_time = time.time()
            while len(batch_ids) < BATCH_SIZE and (time.time() - start_time) < MAX_WAIT_TIME:
                try:
                    next_id = await asyncio.wait_for(live_queue.get(), timeout=1.0)
                    batch_ids.append(next_id)
                except asyncio.TimeoutError:
                    continue

            batch_ids = list(set(batch_ids))

            async with pool.acquire() as conn:
                records = await conn.fetch(
                    """
                    SELECT id, title, content_text, authors
                    FROM articles
                    WHERE id = ANY($1) AND embedding IS NULL
                    """,
                    batch_ids
                )

            if records:
                await embed_and_update(pool, records)

        except Exception as e:
            logger.error(f"Live batch processing failed: {e}. Retrying in 10s.")
            await asyncio.sleep(10)


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    global model, nlp, journalist_blocklist

    logger.info("Loading spaCy Romanian model (CPU)...")
    nlp = spacy.load("ro_core_news_lg")
    logger.info("spaCy ready.")

    logger.info("Loading SentenceTransformer (GPU)...")
    model = SentenceTransformer(MODEL_NAME, device='cuda')
    logger.info("SentenceTransformer ready.")

    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)

    journalist_blocklist = await build_journalist_blocklist(pool)

    asyncio.create_task(maintain_listener())
    asyncio.create_task(periodic_catchup(pool))

    try:
        await asyncio.wait_for(listener_ready.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.critical("Listener failed to connect within 30s.")
        raise

    await run_startup_sweep(pool)
    await live_batch_processor(pool)


if __name__ == '__main__':
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
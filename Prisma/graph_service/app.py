"""
PRISMA Graph Service — Flask API for entity path-finding.

Loads entity_connections into a NetworkX graph at startup.
Exposes:
  POST /paths        — find K shortest node-disjoint paths between two entities
  POST /normalize    — canonicalize an entity name
  GET  /healthz      — health check
  POST /admin/reload — reload graph from DB
"""

from __future__ import annotations

import os
import logging
import math
import threading
import psycopg2
import networkx as nx
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_URL          = os.environ["DATABASE_URL"]
MAX_HOPS        = int(os.getenv("MAX_HOPS",        "3"))
K_PATHS         = int(os.getenv("K_PATHS",         "5"))
QUERY_PMI_FLOOR = float(os.getenv("QUERY_PMI_FLOOR", "0.5"))

# Minimum raw co-mention count for an edge to be used as a path step.
# Eliminates low-evidence connections (addresses, one-off co-mentions, etc.)
MIN_PATH_RAW    = int(os.getenv("MIN_PATH_RAW",    "15"))

# Known Romanian party acronyms — used to detect headline concatenation artifacts
_PARTY_TOKENS: frozenset[str] = frozenset({
    "PSD", "PNL", "USR", "AUR", "UDMR", "PMP", "ALDE", "PRO", "PNTCD", "PP-DD"
})

# Entities blocked from acting as PATH INTERMEDIARIES only.
# They can still be endpoints (user can search for "România").
_INTERMEDIARY_BLACKLIST: frozenset[str] = frozenset({
    "românia",
    "europa",
    "uniunea europeană",
    "statele unite",
    "bucurești",
    "bruxelles",
    "guvernul",
    "parlamentul",
    "senatul",
})

# ── Module-level graph state ───────────────────────────────────────────────────
_graph_lock    = threading.Lock()
_G:             nx.Graph       = nx.Graph()
_degree_map:    dict[str, int] = {}
_hub_blacklist: frozenset[str] = frozenset()


def load_graph_from_db() -> tuple[nx.Graph, dict[str, int], frozenset[str]]:
    """
    Load entity_connections from PostgreSQL into a NetworkX graph.

    No disparity filter — entity_connections already has PMI > 0 and
    MIN_RAW_COMENTIONS=5 applied at graph_builder time. Additional quality
    control is applied at query time via QUERY_PMI_FLOOR and MIN_PATH_RAW.
    """
    logger.info("Loading entity_connections from database...")
    conn   = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT source_entity, target_entity, weight_pmi, weight_raw
        FROM entity_connections
        WHERE weight_pmi > 0
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    logger.info(f"Loaded {len(rows):,} edges from database.")

    G = nx.Graph()
    for source, target, pmi, raw in rows:
        G.add_edge(source, target, weight=pmi, raw=raw)

    logger.info(f"Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    degree_map = dict(G.degree())

    # Hub blacklist: top 0.1% by degree (lowercased) + manual intermediary list
    hub_blacklist: frozenset[str] = _INTERMEDIARY_BLACKLIST
    if degree_map:
        sorted_degrees = sorted(degree_map.values())
        cutoff_idx     = int(len(sorted_degrees) * 0.999)
        hub_threshold  = sorted_degrees[min(cutoff_idx, len(sorted_degrees) - 1)]
        degree_hubs    = frozenset(
            node.lower() for node, deg in degree_map.items()
            if deg >= hub_threshold
        )
        hub_blacklist = degree_hubs | _INTERMEDIARY_BLACKLIST

    logger.info(
        f"Hub blacklist: {len(hub_blacklist)} entries | "
        f"Query PMI floor: {QUERY_PMI_FLOOR} | "
        f"Min path raw: {MIN_PATH_RAW}"
    )
    return G, degree_map, hub_blacklist


def reload_graph() -> None:
    global _G, _degree_map, _hub_blacklist
    G, degree_map, hub_blacklist = load_graph_from_db()
    with _graph_lock:
        _G             = G
        _degree_map    = degree_map
        _hub_blacklist = hub_blacklist
    logger.info("Graph reloaded successfully.")


def adamic_adar_penalty(node: str) -> float:
    """1 / log(1 + degree) — suppresses hub intermediaries in scoring."""
    deg = _degree_map.get(node, 1)
    return 1.0 / math.log(1 + max(deg, 1))


def score_path(path: list[str], G: nx.Graph) -> float:
    """
    geomean(PMI_edges) × Π_intermediaries(adamic_adar_penalty)
    Higher = stronger, more specific connection.
    """
    if len(path) < 2:
        return 0.0

    log_sum = sum(
        math.log(max(G[path[i]][path[i + 1]]['weight'], 1e-9))
        for i in range(len(path) - 1)
    )
    geomean = math.exp(log_sum / (len(path) - 1))

    aa = 1.0
    for node in path[1:-1]:
        aa *= adamic_adar_penalty(node)

    return geomean * aa


def is_artifact_intermediary(node: str) -> bool:
    """
    Detect headline concatenation artifacts and other noise entities
    that should never appear as path intermediaries.

    Examples caught:
    - "PNL PSD"        — two party tokens in one entity
    - "PSD+AUR"        — plus-separated party names
    - "PNL Rareș Bogdan" — party prefix before a person name
    """
    n = node.strip()

    # Contains + separator (PSD+AUR, USR+PNL etc.)
    if '+' in n:
        return True

    # Contains two or more known party acronyms as tokens
    tokens = set(n.split())
    if len(tokens & _PARTY_TOKENS) >= 2:
        return True

    # Starts with a party acronym followed by a person name
    # e.g. "PNL Rareș Bogdan" — party prefix artifact
    parts = n.split(' ', 1)
    if len(parts) == 2 and parts[0] in _PARTY_TOKENS and parts[1][0].isupper():
        return True

    return False


def find_node_disjoint_paths(
    G:             nx.Graph,
    source:        str,
    target:        str,
    k:             int,
    max_hops:      int,
    hub_blacklist: frozenset[str],
    pmi_floor:     float,
    min_raw:       int,
) -> list[list[str]]:
    """
    Find up to K node-disjoint paths from source to target.

    Builds a query-time subgraph filtered by PMI floor and minimum raw
    co-mention count to eliminate low-evidence edges. Uses Yen's
    shortest_simple_paths (cost = 1/PMI, always positive) to generate
    candidates within max_hops. Greedily selects node-disjoint paths,
    rejecting hub-blacklisted and artifact intermediaries.
    """
    if source not in G or target not in G:
        return []

    # Build query-time subgraph: edges above PMI floor AND min raw count
    G_query = nx.Graph()
    for u, v, d in G.edges(data=True):
        if d['weight'] >= pmi_floor and d.get('raw', 0) >= min_raw:
            G_query.add_edge(u, v, weight=d['weight'], raw=d.get('raw', 0))

    # Ensure source and target are in the query graph even if their edges
    # are below thresholds — fallback to full graph for connectivity
    if source not in G_query or target not in G_query:
        logger.warning(
            f"'{source}' or '{target}' disconnected after edge filtering. "
            f"Falling back to full graph for this query."
        )
        G_query = G

    # Cost = 1/PMI: always positive, higher PMI = lower cost = preferred
    def edge_cost(u: str, v: str, d: dict) -> float:
        return 1.0 / max(d['weight'], 1e-9)

    # Collect candidate paths within hop limit
    candidates: list[list[str]] = []
    try:
        for path in nx.shortest_simple_paths(G_query, source, target, weight=edge_cost):
            if len(path) - 1 > max_hops:
                break
            candidates.append(path)
            if len(candidates) >= 100:
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

    # Filter: reject paths with hub-blacklisted or artifact intermediaries
    valid: list[list[str]] = []
    for path in candidates:
        intermediaries = path[1:-1]
        if any(node.lower() in hub_blacklist for node in intermediaries):
            continue
        if any(is_artifact_intermediary(node) for node in intermediaries):
            continue
        valid.append(path)

    # If blacklist/artifact filter rejects everything, return top scored
    # without those filters so the feature always returns something meaningful
    if not valid and candidates:
        logger.warning(
            f"All {len(candidates)} candidates rejected by filters for "
            f"'{source}'→'{target}'. Returning best unfiltered candidates."
        )
        valid = candidates[:20]

    # Score descending
    scored = sorted(
        ((score_path(path, G_query), path) for path in valid),
        key=lambda x: -x[0]
    )

    # Greedy node-disjoint selection
    selected:            list[list[str]] = []
    used_intermediaries: set[str]        = set()

    for _, path in scored:
        intermediaries = set(path[1:-1])
        if intermediaries & used_intermediaries:
            continue
        selected.append(path)
        used_intermediaries |= intermediaries
        if len(selected) >= k:
            break

    return selected


# ── Flask endpoints ────────────────────────────────────────────────────────────

@app.route('/healthz', methods=['GET'])
def healthz():
    with _graph_lock:
        nodes = _G.number_of_nodes()
        edges = _G.number_of_edges()
    return jsonify({'status': 'ok', 'nodes': nodes, 'edges': edges})


@app.route('/normalize', methods=['POST'])
def normalize():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400

    with _graph_lock:
        nodes = list(_G.nodes())

    nl = name.lower()

    # Exact case-insensitive match
    for node in nodes:
        if node.lower() == nl:
            return jsonify({'canonical': node, 'found': True})

    # Single partial match fallback
    matches = [n for n in nodes if nl in n.lower()]
    if len(matches) == 1:
        return jsonify({'canonical': matches[0], 'found': True})

    return jsonify({'canonical': name, 'found': False})


@app.route('/paths', methods=['POST'])
def paths():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'request body required'}), 400

    a        = (data.get('a') or '').strip()
    b        = (data.get('b') or '').strip()
    k        = min(int(data.get('k',        K_PATHS)),  10)
    max_hops = min(int(data.get('max_hops', MAX_HOPS)),  3)

    if not a or not b:
        return jsonify({'error': 'a and b are required'}), 400
    if a.lower() == b.lower():
        return jsonify({'error': 'a and b must be different entities'}), 400

    with _graph_lock:
        G             = _G
        hub_blacklist = _hub_blacklist

    node_list = list(G.nodes())

    def resolve(name: str) -> str | None:
        nl = name.lower()
        for node in node_list:
            if node.lower() == nl:
                return node
        return None

    a_canon = resolve(a)
    b_canon = resolve(b)

    if a_canon is None or b_canon is None:
        missing = [x for x, c in [(a, a_canon), (b, b_canon)] if c is None]
        return jsonify({
            'paths': [],
            'found': False,
            'error': f"Entity not found in graph: {', '.join(missing)}"
        }), 404

    found_paths = find_node_disjoint_paths(
        G, a_canon, b_canon, k, max_hops,
        hub_blacklist, QUERY_PMI_FLOOR, MIN_PATH_RAW
    )

    result_paths = []
    for path in found_paths:
        edges = [
            {
                'from': path[i],
                'to':   path[i + 1],
                'pmi':  round(G[path[i]][path[i + 1]]['weight'], 4),
                'raw':  G[path[i]][path[i + 1]].get('raw', 0),
            }
            for i in range(len(path) - 1)
        ]
        result_paths.append({
            'nodes': path,
            'score': round(score_path(path, G), 4),
            'hops':  len(path) - 1,
            'edges': edges,
        })

    return jsonify({'paths': result_paths, 'found': bool(result_paths)})


@app.route('/admin/reload', methods=['POST'])
def admin_reload():
    threading.Thread(target=reload_graph, daemon=True).start()
    return jsonify({'status': 'reload_started'})


# Load graph on startup
reload_graph()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082)
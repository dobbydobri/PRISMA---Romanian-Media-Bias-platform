// ── Request ──────────────────────────────────────────────────────────────────

export interface SearchRequest {
  query: string;
  top_k?: number;
  filters?: SearchFilters;
}

export interface SearchFilters {
  outlet_ids?: number[];
  date_from?: string; // ISO date string: "YYYY-MM-DD"
  date_to?: string;
  is_fact_check?: boolean;
  topic?: string;
}

// ── Response — snake_case matches API JSON wire format exactly ────────────────

export interface SearchResponse {
  query: string;
  result_count: number;
  confidence: SearchConfidence;
  articles: ArticleSearchResult[];
}

export interface SearchConfidence {
  tier: 'HIGH' | 'MEDIUM' | 'LOW';
  top_rrf_score: number;
  top_cos_sim: number | null;
  agreement_count: number;
}

export interface ArticleSearchResult {
  id: number;
  title: string;
  url: string | null;
  outlet_id: number;
  outlet_name: string;
  published_at: string | null; // ISO datetime string e.g. "2023-08-27T00:00:00Z"
  dense_rank: number | null;
  sparse_rank: number | null;
  cos_sim: number | null;
  ts_score: number | null;
  rrf_score: number;
  cluster_id: number | null;
  sub_cluster_id: number | null;
  score_sensationalism: number | null;
  score_citation_quality: number | null;
  score_rhetoric_intensity: number | null;
}

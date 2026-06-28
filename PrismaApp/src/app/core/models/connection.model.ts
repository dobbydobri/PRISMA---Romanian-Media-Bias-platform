export interface EntitySuggestion {
  name: string;
  label: string;
  article_count: number;
  node_degree: number;
}

export interface ConnectionArticle {
  id: number;
  title: string;
  url: string;
  outlet: string;
  published_at: string | null;
}

export interface DirectConnection {
  article_count: number;
  articles: ConnectionArticle[];
}

export interface PathEdge {
  from: string;
  to: string;
  pmi: number;
  raw: number;
  articles: ConnectionArticle[];
}

export interface IndirectPath {
  nodes: string[];
  score: number;
  hops: number;
  edges: PathEdge[];
}

export interface EntityPathResponse {
  entity_a: string;
  entity_b: string;
  direct: DirectConnection | null;
  indirect: IndirectPath[];
}

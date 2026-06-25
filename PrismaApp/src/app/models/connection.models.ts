export interface EntitySuggestion {
  name: string;
  label: string;
  articleCount: number;
  nodeDegree: number;
}

export interface ConnectionArticle {
  id: number;
  title: string;
  url: string;
  outlet: string;
  publishedAt: string | null;
}

export interface DirectConnection {
  articleCount: number;
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
  entityA: string;
  entityB: string;
  direct: DirectConnection | null;
  indirect: IndirectPath[];
}

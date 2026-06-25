
import { ArticleListItem } from './article.model';
import { FactCheckListItem } from './fact-check.model';

export interface ClusterListItem {
  run_id: number;
  cluster_id: number;
  label_text: string;
  top_tfidf_terms: string[];
  top_entities: string[];
  article_count: number;
  outlet_count: number;
  date_from: string;
  date_to: string;
  is_event_cluster: boolean;
  parent_cluster_id: number | null;
  cluster_title?: string;
}


export interface PaginatedResult<T> {
  items: T[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface ClusterSummary {
  cluster_title?: string;
  neutral_summary?: string;
  key_points: string[];
}

export interface ClusterDetail {
  cluster_id: number;
  run_id: number;
  label_text: string;
  top_tfidf_terms: string[];
  top_entities: string[];
  article_count: number;
  outlet_count: number;
  date_from: string;
  date_to: string;
  is_event_cluster: boolean;
  parent_cluster_id: number | null;
  articles_by_outlet: Record<string, ArticleListItem[]>;
  linked_fact_checks: FactCheckListItem[];
}

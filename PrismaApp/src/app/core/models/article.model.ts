export interface ArticleListItem {
  id: number;
  title: string;
  url: string | null;
  outlet_name: string;
  published_at: string | null;
  cluster_id: number | null;
  cluster_label: string | null;
  score_sensationalism: number | null;
  score_citation_quality: number | null;
  score_rhetoric_intensity: number | null;
  tf_gov_stance: string | null;
  tf_sovereignism: string | null;
  tf_framing: string | null;
  tf_topic: string | null;
}

export interface OutletSummary {
  id: number;
  name: string;
  outlet_type: string;
  url: string | null;
  total_articles: number;
  avg_coalition: number | null;
  avg_eu_axis: number | null;
  avg_sensationalism: number | null;
  avg_citation_quality: number | null;
  avg_rhetoric_intensity: number | null;
  dominant_topic: string | null;
  dominant_framing: string | null;
}

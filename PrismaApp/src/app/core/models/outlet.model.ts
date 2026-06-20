
export interface OutletSummary {
  id: number;
  name: string;
  outletType: string;
  url: string | null;
  totalArticles: number;
  politicalArticles: number;
  avgCoalition: number | null;
  avgEuAxis: number | null;
  avgSensationalism: number | null;
  avgCitationQuality: number | null;
  avgRhetoricIntensity: number | null;
  dominantTopic: string | null;
  dominantFraming: string | null;
}

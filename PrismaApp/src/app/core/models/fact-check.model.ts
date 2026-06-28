export interface FactCheckListItem {
  id: number;
  article_id: number;
  title: string;
  outlet_name: string;
  verdict: string;
  verdict_type: string;
  severity_score: number | null;
  published_at: string; // ISO 8601
  url: string | null;
}

export interface FactCheckBadge {
  has_tier1_match: boolean;
  has_tier2_match: boolean;
  fact_check_count: number;
  max_severity: number | null;
  linked_fact_checks: FactCheckListItem[];
}

export const VERDICT_LABELS: Record<string, string> = {
  true:               'Adevărat',
  partially_true:     'Parțial adevărat',
  unverifiable:       'Neverificabil',
  missing_context:    'Context lipsă',
  truncated:          'Trunchiat',
  partially_false:    'Parțial fals',
  false:              'Fals',
  disinformation:     'Dezinformare',
  fake_news:          'Fake news',
  war_propaganda:     'Propagandă de război',
  deepfake:           'Deepfake',
  doctored_photo:     'Fotografie falsificată',
  ai_generated:       'Generat AI',
  ai_edited:          'Editat AI',
  conspiracy_theory:  'Teorie conspirativă',
  scam:               'Înșelătorie',
  satire:             'Satiră',
};

export type VerdictChipColor = 'green' | 'amber' | 'orange' | 'red';

const VERDICT_CHIP_MAP: Record<string, VerdictChipColor> = {
  true:               'green',
  partially_true:     'green',
  satire:             'green',
  unverifiable:       'amber',
  missing_context:    'amber',
  truncated:          'amber',
  ai_edited:          'amber',
  partially_false:    'orange',
  conspiracy_theory:  'orange',
  ai_generated:       'orange',
  doctored_photo:     'orange',
  false:              'red',
  disinformation:     'red',
  fake_news:          'red',
  war_propaganda:     'red',
  deepfake:           'red',
  scam:               'red',
};

export function verdictChipColor(verdict: string): VerdictChipColor {
  return VERDICT_CHIP_MAP[verdict] ?? 'amber';
}

export function verdictLabel(verdict: string): string {
  return VERDICT_LABELS[verdict] ?? verdict;
}

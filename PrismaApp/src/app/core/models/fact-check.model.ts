export interface FactCheckListItem {
  id: number;
  articleId: number;
  title: string;
  outletName: string;
  verdict: string;
  verdictType: string;
  severityScore: number | null;
  publishedAt: string; // ISO 8601
  url: string | null;
}

export interface FactCheckBadge {
  hasTier1Match: boolean;
  hasTier2Match: boolean;
  factCheckCount: number;
  maxSeverity: number | null;
  linkedFactChecks: FactCheckListItem[];
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

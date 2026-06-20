


export const TOPIC_LABELS: Record<string, string> = {
  culture: 'Cultură',
  economy: 'Economie',
  environment: 'Mediu',
  foreign_affairs: 'Politică Externă',
  health: 'Sănătate',
  justice: 'Justiție',
  politics: 'Politică',
  social: 'Social',
  sports: 'Sport',
  technology: 'Tehnologie',
};


export const FRAMING_LABELS: Record<string, string> = {
  alarmist: 'Alarmist',
  critical: 'Critic',
  human_interest: 'Interes Uman',
  neutral: 'Neutru',
  supportive: 'Suportiv',
};


export const OUTLET_TYPE_LABELS: Record<string, string> = {
  national_agency: 'Agenție Națională', // Agerpres
  news_aggregator: 'Agregator de Știri', // Ziare.com
  investigative: 'Publicație de Investigație', // PressOne, DeFapt.ro
  civic_news: 'Știri Civice', // Buletin de București
  regional_newspaper: 'Ziar Regional', // Deșteptarea, Gazeta de Sud
  fact_checker: 'Verificator de Fapte', // Factual, Veridica
};


export function labelFor(
  map: Record<string, string>,
  key: string | null | undefined,
): string {
  if (!key) return '—';
  return map[key] ?? humanize(key);
}

function humanize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ');
}

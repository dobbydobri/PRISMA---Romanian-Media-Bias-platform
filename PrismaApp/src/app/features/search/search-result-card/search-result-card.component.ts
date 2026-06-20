import { Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ArticleSearchResult } from '../../../core/models/search.model';


const RO_MONTHS = [
  'ian', 'feb', 'mar', 'apr', 'mai', 'iun',
  'iul', 'aug', 'sep', 'oct', 'nov', 'dec',
];

@Component({
  selector: 'app-search-result-card',
  standalone: true,
  imports: [MatIconModule],
  templateUrl: './search-result-card.component.html',
  styleUrl: './search-result-card.component.scss',
})
export class SearchResultCardComponent {
  @Input({ required: true }) article!: ArticleSearchResult;

  // ── Date formatting ────────────────────────────────────────────────────────

  get formattedDate(): string | null {
    if (!this.article.published_at) return null;
    const d = new Date(this.article.published_at);
    if (isNaN(d.getTime())) return null;
    return `${d.getDate()} ${RO_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  }

  // ── Score pill helpers ─────────────────────────────────────────────────────

  
  pillClass(score: number | null, goodWhenHigh: boolean): string {
    if (score === null) return '';
    if (score >= 0.7) return goodWhenHigh ? 'pill--good' : 'pill--bad';
    if (score < 0.3) return goodWhenHigh ? 'pill--bad' : 'pill--good';
    return 'pill--neutral';
  }

  
  fmtScore(score: number): string {
    return score.toFixed(2);
  }

  // ── Relevance bar ──────────────────────────────────────────────────────────

  
  get relevanceWidth(): string {
    const v = this.article.cos_sim;
    if (v === null) return '0%';
    return `${Math.round(v * 100)}%`;
  }

  get relevanceLabel(): string {
    const v = this.article.cos_sim;
    if (v === null) return '';
    return v.toFixed(2);
  }
}

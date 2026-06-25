import { Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ArticleSearchResult } from '../../../core/models/search.model';
import { ArticleScoresComponent } from '../../../shared/components/article-scores/article-scores.component';


const RO_MONTHS = [
  'ian', 'feb', 'mar', 'apr', 'mai', 'iun',
  'iul', 'aug', 'sep', 'oct', 'nov', 'dec',
];

@Component({
  selector: 'app-search-result-card',
  standalone: true,
  imports: [MatIconModule, ArticleScoresComponent],
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

  // ── Relevance bar ──────────────────────────────────────────────────────────

  get relevanceWidth(): string {
    const v = this.article.cos_sim;
    if (v === null) return '0%';
    return `${Math.round(v * 100)}%`;
  }

  get relevanceLabel(): string {
    return this.article.rrf_score.toFixed(2);
  }

  get matchType(): string {
    const hasDense = this.article.dense_rank !== null;
    const hasSparse = this.article.sparse_rank !== null;
    
    if (hasDense && hasSparse) return 'Potrivire hibridă';
    if (hasDense) return 'Potrivire semantică';
    if (hasSparse) return 'Potrivire lexicală';
    return 'Potrivire implicită';
  }
}

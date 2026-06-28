import { Component, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ArticleSearchResult } from '../../../core/models/search.model';
import { ArticleScoresComponent } from '../../../shared/components/article-scores/article-scores.component';
import { RoDatePipe } from '../../../shared/pipes/ro-date.pipe';

@Component({
  selector: 'app-search-result-card',
  standalone: true,
  imports: [MatIconModule, ArticleScoresComponent, RoDatePipe],
  templateUrl: './search-result-card.component.html',
  styleUrl: './search-result-card.component.scss',
})
export class SearchResultCardComponent {
  article = input.required<ArticleSearchResult>();

  // ── Relevance bar ──────────────────────────────────────────────────────────

  get relevanceWidth(): string {
    const v = this.article().cos_sim;
    if (v === null) return '0%';
    return `${Math.round(v * 100)}%`;
  }

  get relevanceLabel(): string {
    return this.article().rrf_score.toFixed(2);
  }

  get matchType(): string {
    const hasDense  = this.article().dense_rank !== null;
    const hasSparse = this.article().sparse_rank !== null;

    if (hasDense && hasSparse) return 'Potrivire hibridă';
    if (hasDense)              return 'Potrivire semantică';
    if (hasSparse)             return 'Potrivire lexicală';
    return 'Potrivire implicită';
  }
}

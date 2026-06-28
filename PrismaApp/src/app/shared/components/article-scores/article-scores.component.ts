import { Component, input } from '@angular/core';

/** Thresholds for diversity label bucketing. */
const DIVERSITY_HIGH_THRESHOLD = 5;
const DIVERSITY_MEDIUM_THRESHOLD = 3;

@Component({
  selector: 'app-article-scores',
  standalone: true,
  templateUrl: './article-scores.component.html',
  styleUrl: './article-scores.component.scss',
})
export class ArticleScoresComponent {
  scoreSensationalism   = input<number | null>(null);
  scoreCitationQuality  = input<number | null>(null);
  scoreRhetoricIntensity = input<number | null>(null);

  pillClass(score: number | null, goodWhenHigh: boolean): string {
    if (score === null) return '';
    if (score >= 0.7) return goodWhenHigh ? 'pill--good' : 'pill--bad';
    if (score < 0.3)  return goodWhenHigh ? 'pill--bad'  : 'pill--good';
    return 'pill--neutral';
  }

  fmtScore(score: number): string {
    return score.toFixed(2);
  }
}

import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-article-scores',
  standalone: true,
  templateUrl: './article-scores.component.html',
  styleUrl: './article-scores.component.scss',
})
export class ArticleScoresComponent {
  @Input() scoreSensationalism: number | null = null;
  @Input() scoreCitationQuality: number | null = null;
  @Input() scoreRhetoricIntensity: number | null = null;

  pillClass(score: number | null, goodWhenHigh: boolean): string {
    if (score === null) return '';
    if (score >= 0.7) return goodWhenHigh ? 'pill--good' : 'pill--bad';
    if (score < 0.3) return goodWhenHigh ? 'pill--bad' : 'pill--good';
    return 'pill--neutral';
  }

  fmtScore(score: number): string {
    return score.toFixed(2);
  }
}

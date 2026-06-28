import { Component, input, output } from '@angular/core';
import { ClusterListItem } from '../../../core/models/cluster.model';
import { FactcheckBadgeComponent } from '../../../shared/components/factcheck-badge/factcheck-badge.component';

/** Outlet-count thresholds for diversity label bucketing. */
const DIVERSITY_HIGH_MIN   = 5;
const DIVERSITY_MEDIUM_MIN = 3;

@Component({
  selector: 'app-topic-card',
  standalone: true,
  imports: [FactcheckBadgeComponent],
  templateUrl: './topic-card.component.html',
  styleUrl: './topic-card.component.scss',
})
export class TopicCardComponent {
  cluster    = input.required<ClusterListItem>();
  cardClick  = output<ClusterListItem>();

  get topTerms(): string[] {
    return (this.cluster().top_tfidf_terms || []).slice(0, 3);
  }

  get perspectiveDiversity(): string {
    const outlets = this.cluster().outlet_count || 1;
    if (outlets >= DIVERSITY_HIGH_MIN)   return 'Mare';
    if (outlets >= DIVERSITY_MEDIUM_MIN) return 'Medie';
    return 'Mică';
  }

  onClick(): void {
    this.cardClick.emit(this.cluster());
  }
}

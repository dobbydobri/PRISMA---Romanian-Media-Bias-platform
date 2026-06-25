import { Component, input, output } from '@angular/core';
import { ClusterListItem } from '../../../core/models/cluster.model';
import { FactcheckBadgeComponent } from '../../../shared/components/factcheck-badge/factcheck-badge.component';

@Component({
  selector: 'app-topic-card',
  standalone: true,
  imports: [FactcheckBadgeComponent],
  templateUrl: './topic-card.component.html',
  styleUrl: './topic-card.component.scss',
})
export class TopicCardComponent {
  cluster = input.required<ClusterListItem>();
  cardClick = output<ClusterListItem>();

  
  get topTerms(): string[] {
    return (this.cluster().top_tfidf_terms || []).slice(0, 3);
  }

  
  pluralRo(n: number, singular: string, plural: string): string {
    return `${n} ${n === 1 ? singular : plural}`;
  }

  get perspectiveDiversity(): string {
    const outlets = this.cluster().outlet_count || 1;
    if (outlets >= 5) return 'Mare';
    if (outlets >= 3) return 'Medie';
    return 'Mică';
  }

  onClick(): void {
    this.cardClick.emit(this.cluster());
  }
}

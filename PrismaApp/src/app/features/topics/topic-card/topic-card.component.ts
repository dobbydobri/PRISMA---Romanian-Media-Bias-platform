import { Component, input, output } from '@angular/core';
import { ClusterListItem } from '../../../core/models/cluster.model';

@Component({
  selector: 'app-topic-card',
  standalone: true,
  imports: [],
  templateUrl: './topic-card.component.html',
  styleUrl: './topic-card.component.scss',
})
export class TopicCardComponent {
  cluster = input.required<ClusterListItem>();
  cardClick = output<ClusterListItem>();

  
  get topTerms(): string[] {
    return this.cluster().topTfidfTerms.slice(0, 3);
  }

  
  pluralRo(n: number, singular: string, plural: string): string {
    return `${n} ${n === 1 ? singular : plural}`;
  }

  onClick(): void {
    this.cardClick.emit(this.cluster());
  }
}

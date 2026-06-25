import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { KeyValuePipe } from '@angular/common';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ClustersService } from '../../../core/api/clusters.service';
import { ClusterDetail, ClusterSummary } from '../../../core/models/cluster.model';
import { ArticleListItem } from '../../../core/models/article.model';
import { ArticleScoresComponent } from '../../../shared/components/article-scores/article-scores.component';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';

@Component({
  selector: 'app-topic-detail',
  standalone: true,
  imports: [RouterLink, MatIconModule, KeyValuePipe, ArticleScoresComponent, EmptyStateComponent],
  templateUrl: './topic-detail.component.html',
  styleUrl: './topic-detail.component.scss',
})
export class TopicDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private clustersService = inject(ClustersService);

  loading = signal(true);
  error = signal<string | null>(null);

  detail = signal<ClusterDetail | null>(null);
  summary = signal<ClusterSummary | null>(null);

  // Expose to template
  articlesByOutlet = computed(() => this.detail()?.articles_by_outlet ?? {});
  hasSummary = computed(() => !!this.summary());
  
  // Format dates locally
  formatDate(dateString: string | null): string | null {
    if (!dateString) return null;
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return null;
    const months = ['ian', 'feb', 'mar', 'apr', 'mai', 'iun', 'iul', 'aug', 'sep', 'oct', 'nov', 'dec'];
    return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
  }

  ngOnInit(): void {
    const runIdStr = this.route.snapshot.paramMap.get('runId');
    const clusterIdStr = this.route.snapshot.paramMap.get('clusterId');

    if (!runIdStr || !clusterIdStr) {
      this.error.set('URL invalid: Parametrii lipsesc.');
      this.loading.set(false);
      return;
    }

    const runId = parseInt(runIdStr, 10);
    const clusterId = parseInt(clusterIdStr, 10);

    this.loading.set(true);

    forkJoin({
      detail: this.clustersService.getClusterDetail(runId, clusterId),
      summary: this.clustersService.getClusterSummary(runId, clusterId).pipe(
        catchError(err => {
          if (err.status === 404) {
            return of(null);
          }
          throw err;
        })
      )
    }).subscribe({
      next: (res) => {
        this.detail.set(res.detail);
        this.summary.set(res.summary);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set('A apărut o eroare la încărcarea detaliilor subiectului.');
        this.loading.set(false);
        console.error('[TopicDetail] Error loading data:', err);
      }
    });
  }
}

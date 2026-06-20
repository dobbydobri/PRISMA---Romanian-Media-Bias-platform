import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { PageEvent, MatPaginatorModule } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';

import { ClustersService } from '../../core/api/clusters.service';
import { ClusterListItem, PaginatedResult } from '../../core/models/cluster.model';
import { TopicCardComponent } from './topic-card/topic-card.component';
import { TopicCardSkeletonComponent } from './topic-card-skeleton/topic-card-skeleton.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';

@Component({
  selector: 'app-topics-page',
  standalone: true,
  imports: [
    MatPaginatorModule,
    MatSelectModule,
    MatFormFieldModule,
    TopicCardComponent,
    TopicCardSkeletonComponent,
    EmptyStateComponent,
  ],
  templateUrl: './topics-page.component.html',
  styleUrl: './topics-page.component.scss',
})
export class TopicsPageComponent implements OnInit {
  private clustersService = inject(ClustersService);

  // ── UI state ─────────────────────────────────────────────────────
  page = signal(1);
  pageSize = signal(20);
  loading = signal(true);
  error = signal<string | null>(null);
  result = signal<PaginatedResult<ClusterListItem> | null>(null);

  // ── Derived state ─────────────────────────────────────────────────
  clusters = computed(() => this.result()?.items ?? []);
  totalCount = computed(() => this.result()?.totalCount ?? 0);
  hasData = computed(() => this.clusters().length > 0);

  
  readonly skeletons = Array.from({ length: 6 });

  ngOnInit(): void {
    this.fetchClusters();
  }

  fetchClusters(): void {
    this.loading.set(true);
    this.error.set(null);

    this.clustersService
      .getClusters(false, this.page(), this.pageSize())
      .subscribe({
        next: (res) => {
          this.result.set(res);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set('Nu s-au putut încărca subiectele.');
          this.loading.set(false);
          console.error('[TopicsPage] API error:', err);
        },
      });
  }

  onPageChange(event: PageEvent): void {
    // Material paginator is 0-indexed; API is 1-indexed
    this.page.set(event.pageIndex + 1);
    this.pageSize.set(event.pageSize);
    this.fetchClusters();
    // Scroll back to top for usability
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  onCardClick(cluster: ClusterListItem): void {
    // Story Detail page is deferred to iteration 2
    console.log(
      '[TopicsPage] Navigate to cluster:',
      cluster.clusterRunId,
      cluster.clusterId,
    );
  }
}

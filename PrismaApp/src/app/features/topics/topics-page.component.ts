import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { PageEvent, MatPaginatorModule } from '@angular/material/paginator';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { ReactiveFormsModule, FormGroup, FormControl } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

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
    MatFormFieldModule,
    MatDatepickerModule,
    MatNativeDateModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatIconModule,
    TopicCardComponent,
    TopicCardSkeletonComponent,
    EmptyStateComponent,
  ],
  templateUrl: './topics-page.component.html',
  styleUrl: './topics-page.component.scss',
})
export class TopicsPageComponent implements OnInit {
  private clustersService = inject(ClustersService);
  private router = inject(Router);

  // ── UI state ─────────────────────────────────────────────────────
  page = signal(1);
  pageSize = signal(15);
  loading = signal(true);
  error = signal<string | null>(null);
  result = signal<PaginatedResult<ClusterListItem> | null>(null);

  dateRange = new FormGroup({
    start: new FormControl<Date | null>(null),
    end: new FormControl<Date | null>(null),
  });

  // ── Derived state ─────────────────────────────────────────────────
  clusters = computed(() => this.result()?.items ?? []);
  totalCount = computed(() => this.result()?.total_count ?? 0);
  hasData = computed(() => this.clusters().length > 0);

  
  readonly skeletons = Array.from({ length: 6 });

  ngOnInit(): void {
    this.fetchClusters();
  }

  fetchClusters(): void {
    this.loading.set(true);
    this.error.set(null);

    const start = this.dateRange.value.start;
    const end = this.dateRange.value.end;

    this.clustersService
      .getClusters(true, this.page(), this.pageSize(), start || null, end || null)
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
    this.router.navigate(['/topics', cluster.run_id, cluster.cluster_id]);
  }

  applyFilter(): void {
    this.page.set(1);
    this.fetchClusters();
  }

  clearFilter(): void {
    this.dateRange.reset();
    this.page.set(1);
    this.fetchClusters();
  }
}

import { Component, inject, signal, computed, OnInit, DestroyRef } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { SearchService } from '../../core/api/search.service';
import { OutletsService } from '../../core/api/outlets.service';
import { AnalysisService, TopicDistributionDto } from '../../core/api/analysis.service';
import { OutletSummary } from '../../core/models/outlet.model';
import {
  SearchRequest,
  SearchFilters,
  SearchResponse,
} from '../../core/models/search.model';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { SearchResultCardComponent } from './search-result-card/search-result-card.component';

@Component({
  selector: 'app-search-page',
  standalone: true,
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
    MatButtonModule,
    MatProgressBarModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatSlideToggleModule,
    EmptyStateComponent,
    SearchResultCardComponent,
  ],
  templateUrl: './search-page.component.html',
  styleUrl: './search-page.component.scss',
})
export class SearchPageComponent implements OnInit {
  private searchService = inject(SearchService);
  private outletsService = inject(OutletsService);
  private analysisService = inject(AnalysisService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);

  // ── Input state ──────────────────────────────────────────────────────────

  
  query = '';

  
  filtersExpanded = signal(false);

  
  filters = signal<SearchFilters>({});

  // Filter panel local state (bound with ngModel, merged into filters() on search)
  selectedOutletIds: number[] = [];
  dateFrom: Date | null = null;
  dateTo: Date | null = null;
  isFactCheck = false;
  selectedTopic: string | null = null;

  // ── Outlet & Topic list for multi-select ─────────────────────────────────────────
  outlets: OutletSummary[] = [];
  topics: TopicDistributionDto[] = [];

  // ── API state ────────────────────────────────────────────────────────────

  loading = signal(false);
  error = signal<string | null>(null);
  result = signal<SearchResponse | null>(null);

  // ── Derived state ────────────────────────────────────────────────────────

  articles = computed(() => this.result()?.articles ?? []);
  confidence = computed(() => this.result()?.confidence ?? null);
  resultCount = computed(() => this.result()?.result_count ?? 0);
  hasResults = computed(() => this.articles().length > 0);
  hasSearched = computed(() => this.result() !== null || this.error() !== null);

  activeFilterCount = computed(() => {
    const f = this.filters();
    let count = 0;
    if (f.outlet_ids?.length) count++;
    if (f.date_from) count++;
    if (f.date_to) count++;
    if (f.is_fact_check) count++;
    if (f.topic) count++;
    return count;
  });

  // ── Lifecycle ────────────────────────────────────────────────────────────

  ngOnInit(): void {
    this.outletsService.getOutlets().subscribe({
      next: (list) => (this.outlets = list),
      error: (err) => console.error('[SearchPage] Failed to load outlets:', err),
    });

    this.analysisService.getTopicDistribution().subscribe({
      next: (list) => (this.topics = list),
      error: (err) => console.error('[SearchPage] Failed to load topics:', err),
    });

    // Parse URL query params and trigger initial search if query exists
    this.route.queryParams.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      let shouldSearch = false;
      
      if (params['q']) {
        this.query = params['q'];
        shouldSearch = true;
      }
      
      if (params['outlet']) {
        const outletIds = params['outlet'].split(',').map((id: string) => parseInt(id, 10)).filter((id: number) => !isNaN(id));
        if (outletIds.length > 0) this.selectedOutletIds = outletIds;
      }
      
      if (params['dateFrom']) {
        const d = new Date(params['dateFrom']);
        if (!isNaN(d.getTime())) this.dateFrom = d;
      }
      
      if (params['dateTo']) {
        const d = new Date(params['dateTo']);
        if (!isNaN(d.getTime())) this.dateTo = d;
      }
      
      if (params['factCheck'] === 'true') {
        this.isFactCheck = true;
      }
      
      if (params['topic']) {
        this.selectedTopic = params['topic'];
      }

      if (shouldSearch && !this.loading()) {
        this.performSearch();
      }
    });
  }

  // ── Actions ──────────────────────────────────────────────────────────────

  onSearch(): void {
    const q = this.query.trim();
    if (!q) return;

    // Update URL query parameters
    const queryParams: any = { q };
    if (this.selectedOutletIds.length) queryParams.outlet = this.selectedOutletIds.join(',');
    if (this.dateFrom) queryParams.dateFrom = this.toIsoDate(this.dateFrom);
    if (this.dateTo) queryParams.dateTo = this.toIsoDate(this.dateTo);
    if (this.isFactCheck) queryParams.factCheck = 'true';
    if (this.selectedTopic) queryParams.topic = this.selectedTopic;

    this.router.navigate([], {
      relativeTo: this.route,
      queryParams,
    });
    
    // The queryParams subscription will trigger performSearch()
  }

  private performSearch(): void {
    const q = this.query.trim();
    if (!q) return;

    // Merge local filter panel state into the filters signal.
    const built: SearchFilters = {};
    if (this.selectedOutletIds.length) built.outlet_ids = this.selectedOutletIds;
    if (this.dateFrom) built.date_from = this.toIsoDate(this.dateFrom);
    if (this.dateTo) built.date_to = this.toIsoDate(this.dateTo);
    if (this.isFactCheck) built.is_fact_check = true;
    if (this.selectedTopic) built.topic = this.selectedTopic;
    this.filters.set(built);

    this.loading.set(true);
    this.error.set(null);
    this.result.set(null);

    const request: SearchRequest = {
      query: q,
      top_k: 20,
      filters: this.activeFilterCount() > 0 ? this.filters() : undefined,
    };

    this.searchService.search(request).subscribe({
      next: (response) => {
        this.result.set(response);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set('Nu s-a putut efectua căutarea.');
        this.loading.set(false);
        console.error('[SearchPage] Search failed:', err);
      },
    });
  }

  onRetry(): void {
    this.performSearch();
  }

  toggleFilters(): void {
    this.filtersExpanded.update((v) => !v);
  }

  clearFilters(): void {
    this.selectedOutletIds = [];
    this.dateFrom = null;
    this.dateTo = null;
    this.isFactCheck = false;
    this.selectedTopic = null;
    this.filters.set({});
    
    // Clear URL params except 'q'
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { q: this.query.trim() || null },
    });
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  
  private toIsoDate(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }
}

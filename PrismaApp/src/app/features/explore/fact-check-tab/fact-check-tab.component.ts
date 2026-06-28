import { Component, inject, signal, OnInit } from '@angular/core';
import { NgClass } from '@angular/common';
import { PageEvent, MatPaginatorModule } from '@angular/material/paginator';
import { MatCardModule } from '@angular/material/card';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

import { FactCheckService } from '../../../core/api/fact-check.service';
import { FactCheckListItem, VERDICT_LABELS, verdictChipColor, verdictLabel } from '../../../core/models/fact-check.model';
import { PaginatedResult } from '../../../core/models/cluster.model';
import { RoDatePipe } from '../../../shared/pipes/ro-date.pipe';

@Component({
  selector: 'app-fact-check-tab',
  standalone: true,
  imports: [
    NgClass,
    RoDatePipe,
    MatCardModule,
    MatSelectModule,
    MatFormFieldModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatButtonModule,
  ],
  templateUrl: './fact-check-tab.component.html',
  styleUrl: './fact-check-tab.component.scss',
})
export class FactCheckTabComponent implements OnInit {
  private factCheckService = inject(FactCheckService);

  items           = signal<FactCheckListItem[]>([]);
  totalCount      = signal<number>(0);
  page            = signal<number>(1);
  loading         = signal<boolean>(false);
  error           = signal<string | null>(null);
  selectedVerdict = signal<string | undefined>(undefined);

  readonly PAGE_SIZE = 20;
  readonly verdictEntries = Object.entries(VERDICT_LABELS);

  ngOnInit(): void {
    this.loadItems();
  }

  loadItems(): void {
    this.loading.set(true);
    this.error.set(null);

    this.factCheckService
      .getFactChecks(this.page(), this.PAGE_SIZE, this.selectedVerdict())
      .subscribe({
        next: (res: PaginatedResult<FactCheckListItem>) => {
          this.items.set(res.items);
          this.totalCount.set(res.total_count);
          this.loading.set(false);
        },
        error: (err: unknown) => {
          this.error.set(
            'Nu s-au putut încărca verificările factuale. Încearcă din nou.',
          );
          this.loading.set(false);
          console.error('[FactCheckTab] API error:', err);
        },
      });
  }

  onVerdictChange(verdict: string | undefined): void {
    this.selectedVerdict.set(verdict);
    this.page.set(1);
    this.loadItems();
  }

  onPageChange(event: PageEvent): void {
    this.page.set(event.pageIndex + 1);
    this.loadItems();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  chipClass(verdict: string): string {
    return `verdict-chip--${verdictChipColor(verdict)}`;
  }

  chipLabel(verdict: string): string {
    return verdictLabel(verdict);
  }
}

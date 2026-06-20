import { Component, Input, OnInit, inject, signal, computed } from '@angular/core';
import { DatePipe, NgClass } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

import { FactCheckService } from '../../../core/api/fact-check.service';
import { FactCheckBadge, verdictChipColor, verdictLabel } from '../../../core/models/fact-check.model';

@Component({
  selector: 'app-factcheck-badge',
  standalone: true,
  imports: [NgClass, DatePipe, MatIconModule, MatButtonModule],
  templateUrl: './factcheck-badge.component.html',
  styleUrl: './factcheck-badge.component.scss',
})
export class FactcheckBadgeComponent implements OnInit {
  @Input({ required: true }) clusterRunId!: number;
  @Input({ required: true }) clusterId!: number;

  private factCheckService = inject(FactCheckService);

  badge   = signal<FactCheckBadge | null>(null);
  showDetails = signal<boolean>(false);

  tierClass = computed<string>(() => {
    const b = this.badge();
    if (!b) return '';
    return b.hasTier1Match ? 'factcheck-badge--tier1' : 'factcheck-badge--tier2';
  });

  isTier1 = computed(() => this.badge()?.hasTier1Match ?? false);

  ngOnInit(): void {
    this.factCheckService
      .getBadge(this.clusterRunId, this.clusterId)
      .subscribe((result) => this.badge.set(result));
  }

  toggleDetails(): void {
    this.showDetails.update((v) => !v);
  }

  chipClass(verdict: string): string {
    return `verdict-chip--${verdictChipColor(verdict)}`;
  }

  chipLabel(verdict: string): string {
    return verdictLabel(verdict);
  }
}

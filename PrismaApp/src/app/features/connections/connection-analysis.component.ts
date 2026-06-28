import { Component, signal, computed, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { DecimalPipe } from '@angular/common';
import { debounceTime, distinctUntilChanged, Subject, switchMap, of } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ConnectionsService } from '../../core/api/connections.service';
import {
  EntitySuggestion,
  EntityPathResponse,
  IndirectPath,
} from '../../core/models/connection.model';

@Component({
  selector: 'app-connection-analysis',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
    DecimalPipe,
    MatAutocompleteModule,
    MatInputModule,
    MatFormFieldModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MatChipsModule,
    MatExpansionModule,
    MatIconModule,
    MatTooltipModule,
    MatDividerModule,
  ],
  templateUrl: './connection-analysis.component.html',
  styleUrl: './connection-analysis.component.scss',
})
export class ConnectionAnalysisComponent {
  private api = inject(ConnectionsService);

  // Input state
  entityAInput = signal('');
  entityBInput = signal('');
  entityASelected = signal<string | null>(null);
  entityBSelected = signal<string | null>(null);

  // Autocomplete suggestions
  suggestionsA = signal<EntitySuggestion[]>([]);
  suggestionsB = signal<EntitySuggestion[]>([]);

  // Results state
  loading = signal(false);
  result = signal<EntityPathResponse | null>(null);
  error = signal<string | null>(null);
  notFound = signal(false);

  // Derived
  canSearch = computed(() => {
    const a = this.entityAInput().trim();
    const b = this.entityBInput().trim();
    return a.length > 0 && b.length > 0 && a !== b;
  });

  private searchA$ = new Subject<string>();
  private searchB$ = new Subject<string>();

  constructor() {
    this.searchA$.pipe(
      debounceTime(200),
      distinctUntilChanged(),
      switchMap(q => q.length >= 2 ? this.api.autocomplete(q) : of([])),
      takeUntilDestroyed(),
    ).subscribe(s => this.suggestionsA.set(s));

    this.searchB$.pipe(
      debounceTime(200),
      distinctUntilChanged(),
      switchMap(q => q.length >= 2 ? this.api.autocomplete(q) : of([])),
      takeUntilDestroyed(),
    ).subscribe(s => this.suggestionsB.set(s));
  }

  onAInput(value: string): void {
    this.entityAInput.set(value);
    this.entityASelected.set(null);
    this.searchA$.next(value);
  }

  onBInput(value: string): void {
    this.entityBInput.set(value);
    this.entityBSelected.set(null);
    this.searchB$.next(value);
  }

  onASelected(value: string): void {
    this.entityASelected.set(value);
    this.entityAInput.set(value);
  }

  onBSelected(value: string): void {
    this.entityBSelected.set(value);
    this.entityBInput.set(value);
  }

  search(): void {
    const a = this.entityAInput().trim();
    const b = this.entityBInput().trim();
    if (!a || !b) return;

    this.loading.set(true);
    this.result.set(null);
    this.error.set(null);
    this.notFound.set(false);

    this.api.findPath(a, b).subscribe({
      next: (res) => {
        this.result.set(res);
        this.loading.set(false);
      },
      error: (err) => {
        if (err.status === 404) {
          this.notFound.set(true);
        } else {
          this.error.set('A apărut o eroare. Încearcă din nou.');
        }
        this.loading.set(false);
      },
    });
  }

  pathLabel(path: IndirectPath): string {
    return path.nodes.join(' → ');
  }
}

import { Component, inject, signal, OnInit, input } from '@angular/core';
import { PageEvent, MatPaginatorModule } from '@angular/material/paginator';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';

import { ArticlesService } from '../../../core/api/articles.service';
import { PaginatedResult } from '../../../core/models/cluster.model';
import { ArticleListItem } from '../../../core/models/article.model';
import { RoDatePipe } from '../../../shared/pipes/ro-date.pipe';

@Component({
  selector: 'app-topic-tab',
  standalone: true,
  imports: [
    RoDatePipe,
    MatCardModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatButtonModule,
    MatChipsModule,
  ],
  templateUrl: './topic-tab.component.html',
  styleUrl: './topic-tab.component.scss',
})
export class TopicTabComponent implements OnInit {
  private articlesService = inject(ArticlesService);

  topic = input.required<string>();

  items      = signal<ArticleListItem[]>([]);
  totalCount = signal<number>(0);
  page       = signal<number>(1);
  loading    = signal<boolean>(false);
  error      = signal<string | null>(null);

  readonly PAGE_SIZE = 20;

  ngOnInit(): void {
    this.loadItems();
  }

  loadItems(): void {
    this.loading.set(true);
    this.error.set(null);

    this.articlesService
      .getArticles(this.page(), this.PAGE_SIZE, this.topic())
      .subscribe({
        next: (res: PaginatedResult<ArticleListItem>) => {
          this.items.set(res.items);
          this.totalCount.set(res.total_count);
          this.loading.set(false);
        },
        error: (err: unknown) => {
          this.error.set('Nu s-au putut încărca articolele. Încearcă din nou.');
          this.loading.set(false);
          console.error('[TopicTab] API error:', err);
        },
      });
  }

  onPageChange(event: PageEvent): void {
    this.page.set(event.pageIndex + 1);
    this.loadItems();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

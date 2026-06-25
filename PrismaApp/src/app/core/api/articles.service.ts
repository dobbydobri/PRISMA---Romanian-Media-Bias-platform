import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from './api-config';
import { PaginatedResult } from '../models/cluster.model';
import { ArticleListItem } from '../models/article.model';

@Injectable({
  providedIn: 'root',
})
export class ArticlesService {
  private http = inject(HttpClient);
  private apiUrl = `${API_BASE_URL}/api/Articles`;

  getArticles(
    page: number = 1,
    pageSize: number = 20,
    topic?: string,
    framing?: string,
    outletId?: number
  ): Observable<PaginatedResult<ArticleListItem>> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('pageSize', pageSize.toString());

    if (topic) {
      params = params.set('topic', topic);
    }
    if (framing) {
      params = params.set('framing', framing);
    }
    if (outletId) {
      params = params.set('outletId', outletId.toString());
    }

    return this.http.get<PaginatedResult<ArticleListItem>>(this.apiUrl, { params });
  }
}

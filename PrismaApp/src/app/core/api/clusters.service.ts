import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from './api-config';
import { ClusterListItem, PaginatedResult } from '../models/cluster.model';

@Injectable({ providedIn: 'root' })
export class ClustersService {
  private http = inject(HttpClient);

  
  getClusters(
    isEvent: boolean,
    page: number = 1,
    pageSize: number = 20,
    sortBy: string = 'articleCount',
  ): Observable<PaginatedResult<ClusterListItem>> {
    const params = new HttpParams()
      .set('isEvent', isEvent)
      .set('page', page)
      .set('pageSize', pageSize)
      .set('sortBy', sortBy);

    return this.http.get<PaginatedResult<ClusterListItem>>(
      `${API_BASE_URL}/api/clusters`,
      { params },
    );
  }
}

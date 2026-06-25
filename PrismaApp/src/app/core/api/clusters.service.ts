import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from './api-config';
import { ClusterListItem, PaginatedResult, ClusterDetail, ClusterSummary } from '../models/cluster.model';

@Injectable({ providedIn: 'root' })
export class ClustersService {
  private http = inject(HttpClient);

  
  getClusters(
    isEvent: boolean,
    page: number = 1,
    pageSize: number = 20,
    dateFrom: Date | null = null,
    dateTo: Date | null = null,
  ): Observable<PaginatedResult<ClusterListItem>> {
    let params = new HttpParams()
      .set('isEvent', isEvent)
      .set('page', page)
      .set('pageSize', pageSize);

    if (dateFrom) params = params.set('dateFrom', dateFrom.toISOString());
    if (dateTo) params = params.set('dateTo', dateTo.toISOString());

    return this.http.get<PaginatedResult<ClusterListItem>>(
      `${API_BASE_URL}/api/clusters`,
      { params },
    );
  }

  getClusterDetail(runId: number, clusterId: number): Observable<ClusterDetail> {
    return this.http.get<ClusterDetail>(
      `${API_BASE_URL}/api/clusters/${runId}/${clusterId}`
    );
  }

  getClusterSummary(runId: number, clusterId: number): Observable<ClusterSummary> {
    return this.http.get<ClusterSummary>(
      `${API_BASE_URL}/api/clusters/${runId}/${clusterId}/summary`
    );
  }
}

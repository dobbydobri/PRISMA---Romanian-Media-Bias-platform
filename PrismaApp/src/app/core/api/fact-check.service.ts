import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { API_BASE_URL } from './api-config';
import { FactCheckListItem, FactCheckBadge } from '../models/fact-check.model';
import { PaginatedResult } from '../models/cluster.model';

@Injectable({ providedIn: 'root' })
export class FactCheckService {
  private http = inject(HttpClient);

  getFactChecks(
    page: number,
    pageSize: number,
    verdict?: string,
  ): Observable<PaginatedResult<FactCheckListItem>> {
    let params = new HttpParams()
      .set('page', page)
      .set('pageSize', pageSize);

    if (verdict !== undefined) {
      params = params.set('verdict', verdict);
    }

    return this.http.get<PaginatedResult<FactCheckListItem>>(
      `${API_BASE_URL}/api/factchecks`,
      { params },
    );
  }

  getBadge(
    clusterRunId: number,
    clusterId: number,
  ): Observable<FactCheckBadge | null> {
    return this.http
      .get<FactCheckBadge>(
        `${API_BASE_URL}/api/factchecks/badge/${clusterRunId}/${clusterId}`,
      )
      .pipe(catchError(() => of(null)));
  }
}

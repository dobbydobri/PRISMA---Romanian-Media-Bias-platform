import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../core/api/api-config';
import {
  EntitySuggestion,
  EntityPathResponse
} from '../models/connection.models';

@Injectable({ providedIn: 'root' })
export class ConnectionsApiService {
  private http = inject(HttpClient);
  private base = `${API_BASE_URL}/api/connections`;

  autocomplete(query: string, limit = 20): Observable<EntitySuggestion[]> {
    const params = new HttpParams().set('q', query).set('limit', limit);
    return this.http.get<EntitySuggestion[]>(`${this.base}/autocomplete`, { params });
  }

  findPath(from: string, to: string): Observable<EntityPathResponse> {
    const params = new HttpParams().set('from', from).set('to', to);
    return this.http.get<EntityPathResponse>(`${this.base}/path`, { params });
  }
}

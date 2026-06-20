import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from './api-config';
import { SearchRequest, SearchResponse } from '../models/search.model';

@Injectable({ providedIn: 'root' })
export class SearchService {
  private http = inject(HttpClient);

  
  search(request: SearchRequest): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${API_BASE_URL}/api/search`, request);
  }
}

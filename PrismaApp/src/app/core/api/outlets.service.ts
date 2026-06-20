import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from './api-config';
import { OutletSummary } from '../models/outlet.model';

@Injectable({ providedIn: 'root' })
export class OutletsService {
  private http = inject(HttpClient);

  
  getOutlets(): Observable<OutletSummary[]> {
    return this.http.get<OutletSummary[]>(`${API_BASE_URL}/api/outlets`);
  }
}

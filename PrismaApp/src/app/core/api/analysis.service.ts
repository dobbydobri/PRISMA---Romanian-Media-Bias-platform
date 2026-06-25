import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { API_BASE_URL } from './api-config';

export interface TopicDistributionDto {
  topic: string;
  count: number;
  percentage: number;
}

@Injectable({ providedIn: 'root' })
export class AnalysisService {
  private http = inject(HttpClient);

  getTopicDistribution(): Observable<TopicDistributionDto[]> {
    return this.http.get<TopicDistributionDto[]>(`${API_BASE_URL}/api/analysis/topic-distribution`);
  }
}

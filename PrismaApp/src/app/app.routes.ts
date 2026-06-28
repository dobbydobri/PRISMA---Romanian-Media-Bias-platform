import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'acasa', pathMatch: 'full' },
  {
    path: 'acasa',
    loadComponent: () =>
      import('./features/home/home-page.component').then(
        (m) => m.HomePageComponent,
      ),
  },
  {
    path: 'topics',
    loadComponent: () =>
      import('./features/topics/topics-page.component').then(
        (m) => m.TopicsPageComponent,
      ),
  },
  {
    path: 'topics/:runId/:clusterId',
    loadComponent: () =>
      import('./features/topics/topic-detail/topic-detail.component').then(
        (m) => m.TopicDetailComponent,
      ),
  },
  {
    path: 'search',
    loadComponent: () =>
      import('./features/search/search-page.component').then(
        (m) => m.SearchPageComponent,
      ),
  },
  {
    path: 'explore',
    loadComponent: () =>
      import('./features/explore/explore.component').then(
        (m) => m.ExploreComponent,
      ),
  },
  {
    path: 'connections',
    loadComponent: () =>
      import('./features/connections/connection-analysis.component').then(
        (m) => m.ConnectionAnalysisComponent,
      ),
  },
];

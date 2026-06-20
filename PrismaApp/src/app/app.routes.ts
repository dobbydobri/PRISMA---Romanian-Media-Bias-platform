import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'topics', pathMatch: 'full' },
  {
    path: 'topics',
    loadComponent: () =>
      import('./features/topics/topics-page.component').then(
        (m) => m.TopicsPageComponent,
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
];

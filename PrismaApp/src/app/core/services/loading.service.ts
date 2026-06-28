import { Injectable, signal } from '@angular/core';

/**
 * Global loading state driven by the loading interceptor.
 * Components that need a local spinner should track their own loading signal;
 * this service only reflects in-flight HTTP requests application-wide.
 */
@Injectable({ providedIn: 'root' })
export class LoadingService {
  private _count = 0;
  readonly loading = signal(false);

  show(): void {
    this.loading.set(++this._count > 0);
  }

  hide(): void {
    if (this._count > 0) this._count--;
    this.loading.set(this._count > 0);
  }
}

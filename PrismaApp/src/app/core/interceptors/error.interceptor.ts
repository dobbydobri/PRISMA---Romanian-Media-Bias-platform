import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

/**
 * Global error interceptor.
 * Logs network and server errors centrally. Individual components still handle
 * their own error signals for user-facing messages; this layer handles logging
 * and provides the hook for future cross-cutting concerns (e.g. 401 redirects).
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError(err => {
      if (err.status === 0) {
        console.error('[HTTP] Network error — no response from server', req.urlWithParams);
      } else if (err.status === 401) {
        console.warn('[HTTP] 401 Unauthorized', req.urlWithParams);
      } else if (err.status >= 500) {
        console.error(`[HTTP] Server error ${err.status}`, req.urlWithParams, err.error);
      }
      return throwError(() => err);
    }),
  );

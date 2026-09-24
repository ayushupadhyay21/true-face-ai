import { HttpErrorResponse } from '@angular/common/http';
import { Envelope } from './api.types';

/** Typed error raised by ApiService for any non-ok envelope or transport failure. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly httpStatus: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function isEnvelope(value: unknown): value is Envelope<unknown> {
  return typeof value === 'object' && value !== null && 'ok' in value && 'error' in value;
}

/**
 * Converts anything thrown by HttpClient (or a non-ok envelope) into an ApiError.
 * HttpClient throws HttpErrorResponse on non-2xx; the backend's envelope is in `err.error`.
 */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) {
      return new ApiError('NETWORK_ERROR', 'Cannot reach the backend at the configured API URL.', 0);
    }
    const body = err.error;
    if (isEnvelope(body) && body.error?.code) {
      return new ApiError(body.error.code, body.error.message, err.status);
    }
    return new ApiError('UNEXPECTED_RESPONSE', `HTTP ${err.status} ${err.statusText || ''}`.trim(), err.status);
  }
  if (isEnvelope(err) && err.error?.code) {
    return new ApiError(err.error.code, err.error.message);
  }
  return new ApiError('UNEXPECTED_RESPONSE', err instanceof Error ? err.message : 'Unexpected error');
}

/** Unwraps a 2xx envelope, throwing ApiError when ok=false or the shape is wrong. */
export function unwrapEnvelope<T>(body: unknown): T {
  if (!isEnvelope(body)) throw new ApiError('UNEXPECTED_RESPONSE', 'Response is not a valid envelope');
  if (!body.ok) {
    throw new ApiError(body.error?.code ?? 'UNEXPECTED_RESPONSE', body.error?.message ?? 'Request failed');
  }
  return body.data as T;
}

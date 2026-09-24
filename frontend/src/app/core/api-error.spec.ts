import { HttpErrorResponse } from '@angular/common/http';
import { ApiError, toApiError, unwrapEnvelope } from './api-error';

describe('toApiError', () => {
  it('reads the backend envelope from a non-2xx HttpErrorResponse', () => {
    const err = new HttpErrorResponse({
      status: 410,
      error: { ok: false, data: null, error: { code: 'SESSION_EXPIRED', message: 'Session expired' } },
    });
    const e = toApiError(err);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.code).toBe('SESSION_EXPIRED');
    expect(e.message).toBe('Session expired');
    expect(e.httpStatus).toBe(410);
  });
  it('maps status 0 to NETWORK_ERROR', () => {
    expect(toApiError(new HttpErrorResponse({ status: 0 })).code).toBe('NETWORK_ERROR');
  });
  it('maps a non-envelope error body to UNEXPECTED_RESPONSE', () => {
    const e = toApiError(new HttpErrorResponse({ status: 502, statusText: 'Bad Gateway', error: '<html>' }));
    expect(e.code).toBe('UNEXPECTED_RESPONSE');
    expect(e.httpStatus).toBe(502);
  });
});

describe('unwrapEnvelope', () => {
  it('returns data for ok envelopes', () => {
    expect(unwrapEnvelope<{ a: number }>({ ok: true, data: { a: 1 }, error: null })).toEqual({ a: 1 });
  });
  it('throws ApiError for ok=false envelopes', () => {
    expect(() => unwrapEnvelope({ ok: false, data: null, error: { code: 'NO_FACE', message: 'x' } })).toThrowError(ApiError);
  });
  it('throws for non-envelope bodies', () => {
    expect(() => unwrapEnvelope('nope')).toThrowError(ApiError);
  });
});

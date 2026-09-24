import { toCameraError } from './camera-errors';

describe('toCameraError', () => {
  const cases: [string, string][] = [
    ['NotAllowedError', 'PERMISSION_DENIED'],
    ['NotFoundError', 'NO_CAMERA'],
    ['NotReadableError', 'CAMERA_IN_USE'],
    ['AbortError', 'CAMERA_IN_USE'],
    ['OverconstrainedError', 'OVERCONSTRAINED'],
    ['SomethingElse', 'UNKNOWN'],
  ];
  for (const [name, code] of cases) {
    it('maps ' + name + ' to ' + code, () => {
      expect(toCameraError({ name }).code).toBe(code);
    });
  }
});

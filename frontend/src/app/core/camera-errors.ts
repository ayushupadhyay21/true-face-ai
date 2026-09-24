export type CameraErrorCode =
  | 'UNSUPPORTED'
  | 'PERMISSION_DENIED'
  | 'NO_CAMERA'
  | 'CAMERA_IN_USE'
  | 'OVERCONSTRAINED'
  | 'DISCONNECTED'
  | 'VIDEO_NOT_READY'
  | 'CAPTURE_FAILED'
  | 'UNKNOWN';

export class CameraError extends Error {
  constructor(
    readonly code: CameraErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'CameraError';
  }
}

const MESSAGES: Record<CameraErrorCode, string> = {
  UNSUPPORTED: 'This browser does not support camera access (navigator.mediaDevices is unavailable). Use a current browser over http://localhost or https.',
  PERMISSION_DENIED: 'Camera permission was denied. Allow camera access for this site in the browser and try again.',
  NO_CAMERA: 'No camera was found. Connect a webcam and try again.',
  CAMERA_IN_USE: 'The camera is in use by another application or could not be started. Close other apps using it and try again.',
  OVERCONSTRAINED: 'The selected camera does not support the requested video settings. Try another camera.',
  DISCONNECTED: 'The camera was disconnected or stopped. Reconnect it and try again.',
  VIDEO_NOT_READY: 'The camera video is not ready yet.',
  CAPTURE_FAILED: 'Could not capture a frame from the camera.',
  UNKNOWN: 'The camera could not be started.',
};

export function cameraErrorMessage(code: CameraErrorCode): string {
  return MESSAGES[code];
}

/** Maps a getUserMedia rejection (DOMException name) to a typed CameraError. */
export function toCameraError(err: unknown): CameraError {
  if (err instanceof CameraError) return err;
  const name = typeof err === 'object' && err !== null && 'name' in err ? String((err as { name: unknown }).name) : '';
  let code: CameraErrorCode;
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
    case 'PermissionDeniedError':
      code = 'PERMISSION_DENIED';
      break;
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      code = 'NO_CAMERA';
      break;
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      code = 'CAMERA_IN_USE';
      break;
    case 'OverconstrainedError':
    case 'ConstraintNotSatisfiedError':
      code = 'OVERCONSTRAINED';
      break;
    case 'TypeError':
      code = 'UNSUPPORTED';
      break;
    default:
      code = 'UNKNOWN';
  }
  return new CameraError(code, MESSAGES[code]);
}

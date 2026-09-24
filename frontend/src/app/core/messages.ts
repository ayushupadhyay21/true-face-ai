import { RecognitionResult, SessionView } from './api.types';

const QUALITY_REASON_TEXT: Record<string, string> = {
  FACE_TOO_SMALL: 'Move closer',
  TOO_DARK: 'More light needed',
  TOO_BRIGHT: 'Too bright - reduce direct light',
  TOO_BLURRY: 'Hold still',
  NOT_FRONTAL: 'Face the camera',
  LOW_CONTRAST: 'Low contrast - improve the lighting',
  LOW_DETECTION_CONFIDENCE: 'Face not clear - face the camera in good light',
  LANDMARKS_OUTSIDE_FACE: 'Keep your whole face inside the frame',
};

/** Friendly text for a backend quality_reason code. */
export function qualityReasonText(reason: string | null | undefined): string {
  if (!reason) return 'Adjust your position';
  return QUALITY_REASON_TEXT[reason] ?? reason.replace(/_/g, ' ').toLowerCase();
}

const ERROR_TEXT: Record<string, string> = {
  NO_FACE: 'No face detected.',
  MULTIPLE_FACES: 'More than one face was in view. Only one person may be in front of the camera.',
  LOW_FACE_QUALITY: 'Face quality too low.',
  LIVENESS_FAILED: 'Liveness check failed.',
  CHALLENGE_FAILED: 'The head-movement challenge was not completed in time.',
  SESSION_EXPIRED: 'The session expired. Please try again.',
  SESSION_NOT_FOUND: 'The session was not found on the server (it may have restarted).',
  SESSION_STATE: 'The session is no longer accepting frames.',
  UNKNOWN_PERSON: 'Unknown person.',
  PERSON_NOT_FOUND: 'Person not found.',
  INVALID_FRAME: 'The camera frame could not be read by the server.',
  INVALID_REQUEST: 'The request was rejected by the server.',
  MODEL_UNAVAILABLE: 'A required model is not available on the backend.',
  NOT_CALIBRATED: 'The recognition threshold is not calibrated yet.',
  DATABASE_ERROR: 'The backend database is unavailable.',
  INTERNAL_ERROR: 'The backend hit an internal error.',
  NETWORK_ERROR: 'Cannot reach the backend. Is it running on http://localhost:8000?',
  UNEXPECTED_RESPONSE: 'Unexpected response from the backend.',
};

/** Friendly text for an error code; falls back to the server message when the code is unknown. */
export function errorCodeText(code: string | null | undefined, fallback?: string): string {
  if (code && ERROR_TEXT[code]) return ERROR_TEXT[code];
  return fallback || code || 'Something went wrong.';
}

export interface LiveStatus {
  /** Short status line, e.g. "Detecting face..." */
  text: string;
  /** Large instruction for the ACTIVE phase, e.g. "Turn your head to your LEFT". */
  instruction: string | null;
  /** Progress for the current phase, 0..1, or null when not applicable. */
  progress: number | null;
  progressLabel: string | null;
  /** True when the text describes a problem the user must fix. */
  warning: boolean;
}

/** Derives the live status shown during a running session from the latest SessionView. */
export function liveStatus(view: SessionView | null): LiveStatus {
  const base: LiveStatus = { text: 'Detecting face...', instruction: null, progress: null, progressLabel: null, warning: false };
  if (!view) return base;

  const frame = view.frame;
  if (frame?.frame_error === 'NO_FACE') {
    return { ...base, ...phaseProgress(view), text: 'Detecting face... (no face in view)', warning: true };
  }
  if (frame?.frame_error === 'MULTIPLE_FACES') {
    return { ...base, text: 'More than one face in view', warning: true };
  }
  if (frame?.frame_error === 'LOW_FACE_QUALITY') {
    return {
      ...base,
      ...phaseProgress(view),
      text: `Checking quality... ${qualityReasonText(frame.quality?.quality_reason)}`,
      warning: true,
    };
  }

  if (view.phase === 'PASSIVE') {
    if (!frame) return base;
    return { ...base, ...phaseProgress(view), text: `Checking liveness... (${view.passive_frames}/${view.passive_frames_required})` };
  }
  if (view.phase === 'ACTIVE') {
    return {
      ...base,
      ...phaseProgress(view),
      text: 'Follow the instruction',
      instruction: view.instruction,
    };
  }
  return { ...base, text: view.status === 'PASSED' ? 'Checks passed, finishing...' : 'Finishing...' };
}

function phaseProgress(view: SessionView): Pick<LiveStatus, 'progress' | 'progressLabel' | 'instruction'> {
  if (view.phase === 'ACTIVE' && view.total_actions > 0) {
    return {
      progress: view.completed_actions / view.total_actions,
      progressLabel: `Action ${Math.min(view.completed_actions + 1, view.total_actions)} of ${view.total_actions} (${view.completed_actions} done)`,
      instruction: view.instruction,
    };
  }
  if (view.phase === 'PASSIVE' && view.passive_frames_required > 0) {
    return {
      progress: Math.min(1, view.passive_frames / view.passive_frames_required),
      progressLabel: `Liveness frames ${view.passive_frames}/${view.passive_frames_required}`,
      instruction: null,
    };
  }
  return { progress: null, progressLabel: null, instruction: null };
}

export type OutcomeTone = 'success' | 'neutral' | 'danger';

export interface RecognitionOutcome {
  title: string;
  tone: OutcomeTone;
  detail: string;
  /** Only set for KNOWN results. Never set for liveness failures. */
  person: { name: string; externalId: string | null } | null;
  similarity: number | null;
}

/** Maps a /recognition/complete result to the card shown to the user. */
export function recognitionOutcome(r: RecognitionResult): RecognitionOutcome {
  const similarity = typeof r.similarity === 'number' ? r.similarity : null;
  switch (r.result) {
    case 'KNOWN':
      return {
        title: 'KNOWN PERSON',
        tone: 'success',
        detail: 'Live face matched an enrolled person.',
        person: r.person ? { name: r.person.name, externalId: r.person.external_id ?? null } : null,
        similarity,
      };
    case 'UNKNOWN':
      return { title: 'UNKNOWN PERSON', tone: 'neutral', detail: 'Live face, but no enrolled person matched.', person: null, similarity };
    case 'LIVENESS_FAILED':
      // Never reveal identity information for a failed liveness check.
      return { title: 'LIVENESS FAILED', tone: 'danger', detail: 'The face did not pass the liveness check.', person: null, similarity: null };
    case 'CHALLENGE_FAILED':
      return { title: 'CHALLENGE FAILED', tone: 'danger', detail: errorCodeText('CHALLENGE_FAILED'), person: null, similarity: null };
    case 'MULTIPLE_FACES':
      return { title: 'MULTIPLE FACES', tone: 'danger', detail: errorCodeText('MULTIPLE_FACES'), person: null, similarity: null };
    case 'EXPIRED':
    case 'SESSION_EXPIRED':
      return { title: 'SESSION EXPIRED', tone: 'danger', detail: errorCodeText('SESSION_EXPIRED'), person: null, similarity: null };
    default:
      return {
        title: 'VERIFICATION FAILED',
        tone: 'danger',
        detail: errorCodeText(r.error_code ?? r.result),
        person: null,
        similarity: null,
      };
  }
}

/** Formats the `poses` field of an enrollment result (list or pose->count map). */
export function formatPoses(poses: string[] | Record<string, number> | null | undefined): string {
  if (!poses) return '-';
  if (Array.isArray(poses)) return poses.length ? poses.join(', ') : '-';
  const entries = Object.entries(poses);
  return entries.length ? entries.map(([k, v]) => `${k} x${v}`).join(', ') : '-';
}

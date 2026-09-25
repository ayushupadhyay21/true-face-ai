export interface ApiErrorBody {
  code: string;
  message: string;
}

/** Every backend response (including HTTP errors) uses this envelope. */
export interface Envelope<T> {
  ok: boolean;
  data: T | null;
  error: ApiErrorBody | null;
}

export type ErrorCode =
  | 'NO_FACE'
  | 'MULTIPLE_FACES'
  | 'LOW_FACE_QUALITY'
  | 'LIVENESS_FAILED'
  | 'CHALLENGE_FAILED'
  | 'SESSION_EXPIRED'
  | 'SESSION_NOT_FOUND'
  | 'SESSION_STATE'
  | 'UNKNOWN_PERSON'
  | 'PERSON_NOT_FOUND'
  | 'INVALID_FRAME'
  | 'INVALID_REQUEST'
  | 'MODEL_UNAVAILABLE'
  | 'NOT_CALIBRATED'
  | 'DATABASE_ERROR'
  | 'INTERNAL_ERROR'
  // client-side codes
  | 'NETWORK_ERROR'
  | 'UNEXPECTED_RESPONSE';

export interface HealthData {
  status: 'ok' | 'degraded';
  database: Record<string, unknown> | null;
  database_ok: boolean;
}

export interface ModelsHealthData {
  models: unknown;
  identity_threshold: number | null;
  calibrated: boolean;
  liveness_threshold: number;
  providers: unknown;
}

export interface Person {
  id: string;
  name: string;
  external_id: string | null;
  status: string;
  embedding_count: number;
  created_at: string;
  updated_at: string;
}

export interface PersonCreateRequest {
  name: string;
  external_id?: string;
}

export type SessionStatus = 'CREATED' | 'IN_PROGRESS' | 'PASSED' | 'FAILED' | 'EXPIRED';
export type SessionPhase = 'PASSIVE' | 'ACTIVE' | 'DONE';
export type ChallengeAction = 'LOOK_LEFT' | 'LOOK_RIGHT' | 'LOOK_UP' | 'LOOK_DOWN' | 'BLINK' | 'CENTER';
export type FrameError = 'NO_FACE' | 'MULTIPLE_FACES' | 'LOW_FACE_QUALITY';

export interface FrameQuality {
  quality_reason: string | null;
  [key: string]: unknown;
}

export interface FrameInfo {
  face_count: number;
  frame_error: FrameError | null;
  quality: FrameQuality | null;
  liveness_frame_score: number | null;
  timings_ms: Record<string, number>;
}

export interface SessionView {
  session_id: string;
  session_type: 'ENROLLMENT' | 'RECOGNITION';
  status: SessionStatus;
  phase: SessionPhase;
  current_action: ChallengeAction | null;
  instruction: string | null;
  completed_actions: number;
  total_actions: number;
  passive_frames: number;
  passive_frames_required: number;
  expires_at: string;
  error_code: string | null;
  message: string | null;
  frame?: FrameInfo;
}

export interface FrameRequest {
  session_id: string;
  frame_number: number;
  image_base64: string;
}

export interface EnrollmentResult {
  session_id?: string;
  result: string; // "ENROLLED" or a failure result such as "LIVENESS_FAILED"
  embeddings_stored?: number;
  poses?: string[] | Record<string, number>;
  liveness_score?: number;
  error_code?: string;
}

export type RecognitionResultKind =
  | 'KNOWN'
  | 'UNKNOWN'
  | 'LIVENESS_FAILED'
  | 'CHALLENGE_FAILED'
  | 'MULTIPLE_FACES'
  | 'EXPIRED';

export interface RecognitionResult {
  session_id?: string;
  result: RecognitionResultKind | string;
  similarity?: number | null;
  liveness_score?: number;
  threshold?: number;
  person?: { id: string; name: string; external_id: string | null };
  error_code?: string;
}

// ---------- Live multi-face tracking (/api/live/*) ----------

export type LiveFaceState = 'CHECKING' | 'LIVE' | 'KNOWN' | 'UNKNOWN' | 'SPOOF' | 'TOO_SMALL';

export interface LiveStartData {
  live_id: string;
}

export interface LiveFrameRequest {
  live_id: string;
  frame_number: number;
  image_base64: string;
}

export interface LiveFace {
  track_id: number;
  /** [x1, y1, x2, y2] normalized 0..1 in RAW (un-mirrored) image coordinates. */
  bbox: [number, number, number, number];
  state: LiveFaceState;
  label: string;
  liveness_score: number | null;
  name: string | null;
  person_id: string | null;
  similarity: number | null;
}

export interface LiveFrameResult {
  frame_width: number;
  frame_height: number;
  face_count: number;
  threshold: number | null;
  timings_ms: { detection?: number; total?: number; [key: string]: number | undefined };
  faces: LiveFace[];
}

export interface LiveStopResult {
  stopped: boolean;
}

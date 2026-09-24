/** Local backend (FastAPI). Its CORS config allows http://localhost:4200. */
export const API_BASE_URL = 'http://localhost:8000';

/** Pause between one frame response and the next capture (ms). */
export const FRAME_DELAY_MS = 120;

/** Max captured frame size; frames are scaled down to fit, never up. */
export const CAPTURE_MAX_WIDTH = 640;
export const CAPTURE_MAX_HEIGHT = 480;
export const JPEG_QUALITY = 0.85;

/** Consecutive INVALID_FRAME errors tolerated before the session loop gives up. */
export const MAX_CONSECUTIVE_INVALID_FRAMES = 5;

/** How often the status bar re-checks /health (ms). */
export const HEALTH_POLL_MS = 30_000;

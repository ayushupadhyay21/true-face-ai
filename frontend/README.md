# Frontend (Angular)

Angular 21 single-page app for the local face-recognition + liveness research backend.
Plain Angular + CSS (standalone components, signals); no UI libraries.

## Run

```bash
npm install
npm start          # ng serve on http://localhost:4200
```

Open http://localhost:4200. The backend must be running on `http://localhost:8000`
(configured in `src/app/core/config.ts`; the backend's CORS allows `http://localhost:4200`).

Other commands:

```bash
npm run build                 # production build -> dist/frontend
npx ng test --watch=false     # unit tests (Vitest + jsdom, no browser needed)
```

## Pages

- `/recognize` (default) - Face Verification: camera, live status, final result card
  (KNOWN / UNKNOWN / LIVENESS FAILED / CHALLENGE FAILED / MULTIPLE FACES / SESSION EXPIRED / error).
  A liveness failure never shows a name.
- `/enroll` - creates a person (name, optional external ID), then runs an enrollment session.
- The status bar shows `/health` (database) and `/health/models` (`calibrated`) and shows a
  warning banner when the database is down or the models are not calibrated.

## Camera and frames

- The camera is opened with `getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false })`.
  When several cameras exist a dropdown lets you choose one.
- **Mirroring:** the `<video>` preview is mirrored with CSS (`transform: scaleX(-1)`) only for
  comfort. Captured frames are drawn to the canvas **un-mirrored** (raw camera image), because the
  backend's LEFT/RIGHT head-turn logic expects raw frames. "Turn your head to your LEFT" means the
  user's own left.
- **Capture rate:** frames are sent strictly one at a time: capture -> POST -> wait for the response
  -> pause ~120 ms -> next frame. There are never parallel requests, so the effective rate is
  `1 / (server processing time + 120 ms)` (typically a few frames per second). Frames are JPEG
  (quality 0.85), at most 640x480, sent as a data URL with a strictly increasing `frame_number`.
- The loop stops when the session status is PASSED, FAILED or EXPIRED, then the matching
  `/complete` endpoint is called once. It also stops on SESSION_EXPIRED / SESSION_NOT_FOUND /
  SESSION_STATE (or any other API error); INVALID_FRAME is skipped up to 5 times in a row.
- Camera tracks are stopped after completion, on errors, on Cancel and when leaving the page.
- Frames are never stored (no localStorage / IndexedDB / downloads).

## Layout

```
src/app/
  core/
    config.ts                  API base URL and capture constants
    api.types.ts               response/request interfaces
    api-error.ts               envelope -> ApiError mapping
    api.service.ts             typed HttpClient calls
    camera.service.ts          getUserMedia, device list, raw frame capture
    camera-errors.ts           DOMException -> CameraError mapping
    session-runner.service.ts  sequential frame loop + completion
    messages.ts                status text, quality hints, result cards
    health.service.ts          /health polling
  shared/                      status bar, live status, camera select
  pages/enroll, pages/recognize
```

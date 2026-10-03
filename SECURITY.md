# Security Notes and Limitations

This is a research prototype. **It is not claimed to be spoof-proof.** Everything below describes what the implementation enforces and what it cannot enforce.

## Enforced rules

| Rule | Where |
|---|---|
| Identity is searched only after the session status is `PASSED` (passive and active liveness). The embeddings computed earlier are never searched before that. | `SessionEngine.complete`; test `test_identity_never_searched_before_pass` |
| A failed liveness check reveals no identity: the result is `LIVENESS_FAILED` / `CHALLENGE_FAILED` with no name and no similarity. | `complete()`; tests `test_spoof_fails_passive_and_hides_identity`, `test_multiple_faces_via_api` |
| 2 or more faces fail the session with `MULTIPLE_FACES`. The system never picks one of them. | `FaceDetectionService`, engine |
| Below-threshold similarity returns `UNKNOWN`, never the closest person. | `_complete_recognition` |
| The challenge sequence comes from a CSPRNG (`secrets.SystemRandom`), is different every session, and is revealed one action at a time. | `challenge.generate_actions` |
| The frontend cannot claim success: the backend computes every decision from the frames it receives. There is no "passed" field in any request. | API schemas (`extra="forbid"`) |
| Replay protection: `frame_number` must strictly increase, frames must keep arriving (at most 3 s gap), and a session accepts no frames after it ends. | `process_frame` |
| Expiry: the session lasts 60 s, each action 12 s. `/complete` is allowed only in a short grace window. | engine |
| A session completes once: `completed_at` is set with an atomic `UPDATE … WHERE completed_at IS NULL`, and a second completion returns 409. | `mark_completed` |
| Face swap mid-session: the face centre may not jump by more than 0.8 × the face width between frames, and the final CENTER embedding must match the passive-phase embedding. | engine |
| A face that already matches another person cannot be enrolled under a new identity. | `_complete_enrollment` |
| No raw camera frames are stored. Frames are processed in memory only; `STORE_RAW_FRAMES=false` and no code path writes frames. **Exception:** live mode, when it auto-buckets an unmatched face (`LIVE_AUTO_ENROLL_UNKNOWN=true`, default), stores the small aligned 112x112 crop of that face (never the raw frame) so an operator can name them later. See DATABASE.md "Unassigned people". | frame_analyzer / routes / live_tracker |
| No stack traces in responses. Unhandled errors return `INTERNAL_ERROR`; details go to `logs/backend.log`. | `main.py` |
| No secrets in code. DB credentials come from `.env` (git-ignored); the admin password is only prompted for. | config, `setup_database.py` |

## Liveness modes

`ACTIVE_LIVENESS_ENABLED` (in `.env`) selects the mode.

- **`false`: passive only.** Fully automatic, with no user instructions. The session passes once the mean PAD score over 5 good frontal frames reaches the threshold. Nothing in this mode tests for a pre-recorded video (replay attack), and the end-of-session "same person" CENTER check is skipped. Security then depends entirely on the passive model.
- **`true`: passive plus the random challenge.** This is the stronger setting against video replay.

## Live multi-face mode (`/api/live/*`, Live page)

This mode shows every face in view, with a box and a name. It deliberately relaxes one verification rule:

- **Several faces are allowed.** Each face is tracked and judged on its own.

Each face still gets passive liveness (the mean of a rolling window of up to 10 frame scores, starting after at least 5 frames), and, if `LIVE_ACTIVE_LIVENESS_ENABLED=true` (default), it must also blink once before it is ever named -- evaluated with the same BLINK code as a verification session (`challenge.py`). This is a separate switch from the Recognize/Enroll session's `ACTIVE_LIVENESS_ENABLED`; either can be on independently. It runs **silently**: the face box shows the same "Look at the camera" label throughout and no prompt is ever shown, and it is BLINK-only (never a head-turn) because a real person blinks on their own within a few seconds without being asked, but does not turn their head on their own -- a random pool including head-turns would leave a cooperative user stuck. There is no hard failure or expiry either: a track that times out waiting for a blink is simply given a fresh window and keeps trying, since Live View has no bounded session lifecycle to fail out of. With this off, Live View falls back to passive-only, same as before.

Rules that still hold:

- A face's name is returned only while that face is LIVE and its similarity is at or above the calibrated threshold.
- A face judged SPOOF has its cached identity cleared.
- If a new embedding stops matching a face's own history, that face's identity is reset (including its blink-check progress: the new face must blink again).

With this on, a static printed photo or a screen replay that never blinks can never be named. It is still weaker than a verification session against a pre-recorded video of the real person blinking on their own -- use the Recognize page when a single, stronger decision is needed.

## Known limitations (not mitigated)

1. **Passive PAD coverage is unknown.** The Silent-Face training data is undisclosed, and the model runs on SCRFD crops rather than its native detector's. Only the attacks actually recorded and evaluated (EVALUATION.md) have evidence.
2. **Frame freshness cannot be proven.** A client can inject any image stream, for example a virtual camera. Increasing frame numbers and timing stop naive replays of captured API traffic, but not a live injected stream. The random challenge is the main defence: a pre-recorded video would have to perform the right actions in the right order within the time limits.
3. **An attacker can respond to the challenge live.** Examples: a real-time face reenactment or deepfake, a 3D mask, or a person holding up a flexible printed photo and bending it. These are out of scope for these models.
4. **Head-pose actions use 2D landmark ratios.** A printed photo that is physically rotated or tilted can change these ratios. The passive PAD score, which is monitored on every frame, is the only defence against that.
5. **Blink detection runs at 5–8 FPS.** A very fast blink between two captured frames can be missed. The user then just blinks again within the 12 s window. A replay video containing a blink can satisfy BLINK only if it also satisfies the other random actions in order.
6. **Scores are returned to the client** (per-frame liveness score, quality metrics). This helps research and debugging, but it would help an attacker tune an attack. Remove them before any non-research use.
7. **The identity threshold was calibrated on LFW** (web photos), not on webcam frames. Re-calibrate it on local data before drawing conclusions.
8. **Mirroring:** clients must send raw, un-mirrored frames. A mirrored stream swaps LEFT and RIGHT (`CAMERA_MIRRORED=true` compensates).
9. **PostgreSQL listens on all interfaces** on the audit machine (`listen_addresses='*'`). Local use only: set `listen_addresses='localhost'` in `postgresql.conf`, or firewall port 5432.
10. **No authentication** on the API. It binds to localhost for local research only. Do not expose it on a network.

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
| No raw images are stored. Frames are processed in memory only; `STORE_RAW_FRAMES=false` and no code path writes frames. | frame_analyzer / routes |
| No stack traces in responses. Unhandled errors return `INTERNAL_ERROR`; details go to `logs/backend.log`. | `main.py` |
| No secrets in code. DB credentials come from `.env` (git-ignored); the admin password is only prompted for. | config, `setup_database.py` |

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

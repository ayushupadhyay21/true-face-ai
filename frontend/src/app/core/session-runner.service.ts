import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';

import { toApiError } from './api-error';
import { FrameRequest, SessionStatus, SessionView } from './api.types';
import { CameraError, cameraErrorMessage } from './camera-errors';
import { CameraService } from './camera.service';
import { FRAME_DELAY_MS, MAX_CONSECUTIVE_INVALID_FRAMES } from './config';
import { errorCodeText, liveStatus } from './messages';

export type RunnerState = 'idle' | 'camera' | 'starting' | 'running' | 'completing' | 'done' | 'error';

export type SessionOutcome<T> =
  | { kind: 'completed'; result: T }
  | { kind: 'error'; code: string; message: string };

export interface SessionCallbacks<T> {
  /** Creates the backend session (and anything needed before it, e.g. the person). */
  start: () => Promise<SessionView>;
  frame: (req: FrameRequest) => Promise<SessionView>;
  complete: (sessionId: string) => Promise<T>;
}

const TERMINAL: ReadonlySet<SessionStatus> = new Set(['PASSED', 'FAILED', 'EXPIRED']);
/** Codes whose server message is more useful than our generic text. */
const SERVER_MESSAGE_CODES: ReadonlySet<string> = new Set(['INVALID_REQUEST', 'UNEXPECTED_RESPONSE']);
const NOT_READY_RETRY_MS = 200;
const NOT_READY_MAX_RETRIES = 25;

export function isTerminalStatus(status: SessionStatus): boolean {
  return TERMINAL.has(status);
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Runs one liveness session: start camera -> start session -> frame loop -> complete.
 * Frames are sent strictly one at a time (capture, POST, await, pause, repeat).
 * Frames are never stored: each data URL only lives for the duration of its request.
 */
@Injectable()
export class SessionRunner implements OnDestroy {
  private readonly camera = inject(CameraService);

  readonly state = signal<RunnerState>('idle');
  readonly view = signal<SessionView | null>(null);
  readonly framesSent = signal(0);
  readonly status = computed(() => liveStatus(this.view()));
  readonly busy = computed(() => ['camera', 'starting', 'running', 'completing'].includes(this.state()));

  private runId = 0;

  async run<T>(video: HTMLVideoElement, cb: SessionCallbacks<T>): Promise<SessionOutcome<T> | null> {
    const id = ++this.runId;
    const cancelled = () => id !== this.runId;
    this.view.set(null);
    this.framesSent.set(0);

    try {
      this.state.set('camera');
      await this.camera.start(video);
      if (cancelled()) return null;

      this.state.set('starting');
      let view = await cb.start();
      if (cancelled()) return null;
      this.view.set(view);
      this.state.set('running');

      let frameNumber = 0;
      let invalidStreak = 0;
      let notReady = 0;

      while (!isTerminalStatus(view.status)) {
        if (this.camera.disconnected()) throw new CameraError('DISCONNECTED', cameraErrorMessage('DISCONNECTED'));

        let image: string;
        try {
          image = this.camera.captureFrame();
          notReady = 0;
        } catch (err) {
          if (err instanceof CameraError && err.code === 'VIDEO_NOT_READY' && ++notReady <= NOT_READY_MAX_RETRIES) {
            await sleep(NOT_READY_RETRY_MS);
            if (cancelled()) return null;
            continue;
          }
          throw err;
        }

        try {
          view = await cb.frame({ session_id: view.session_id, frame_number: frameNumber++, image_base64: image });
          invalidStreak = 0;
        } catch (err) {
          const apiErr = toApiError(err);
          // INVALID_FRAME: skip and send the next frame (up to the limit). Any other error
          // (incl. SESSION_EXPIRED / SESSION_NOT_FOUND / SESSION_STATE) stops the loop.
          if (apiErr.code !== 'INVALID_FRAME' || ++invalidStreak >= MAX_CONSECUTIVE_INVALID_FRAMES) throw apiErr;
        }
        if (cancelled()) return null;
        this.framesSent.update((n) => n + 1);
        this.view.set(view);

        if (!isTerminalStatus(view.status)) {
          await sleep(FRAME_DELAY_MS);
          if (cancelled()) return null;
        }
      }

      this.state.set('completing');
      const result = await cb.complete(view.session_id);
      if (cancelled()) return null;
      this.finish('done');
      return { kind: 'completed', result };
    } catch (err) {
      if (cancelled()) return null;
      this.finish('error');
      return this.toOutcome(err);
    }
  }

  /** Stops any running loop (without calling /complete) and releases the camera. */
  cancel(): void {
    this.runId++;
    this.camera.stop();
    if (this.busy()) this.state.set('idle');
  }

  reset(): void {
    this.cancel();
    this.view.set(null);
    this.state.set('idle');
  }

  ngOnDestroy(): void {
    this.cancel();
  }

  private finish(state: RunnerState): void {
    this.camera.stop();
    this.state.set(state);
  }

  private toOutcome<T>(err: unknown): SessionOutcome<T> {
    if (err instanceof CameraError) return { kind: 'error', code: err.code, message: err.message };
    const e = toApiError(err);
    const message = SERVER_MESSAGE_CODES.has(e.code) ? e.message : errorCodeText(e.code, e.message);
    return { kind: 'error', code: e.code, message };
  }
}

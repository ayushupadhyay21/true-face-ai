import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, computed, inject, signal, viewChild } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { toApiError } from '../../core/api-error';
import { LiveFace } from '../../core/api.types';
import { CameraError, cameraErrorMessage } from '../../core/camera-errors';
import { CameraService } from '../../core/camera.service';
import { LIVE_FRAME_DELAY_MS, MAX_CONSECUTIVE_INVALID_FRAMES } from '../../core/config';
import { errorCodeText } from '../../core/messages';
import { CameraSelectComponent } from '../../shared/camera-select.component';
import { IconComponent } from '../../shared/icon.component';
import {
  drawnVideoRect,
  faceStyle,
  formatSimilarity,
  mirroredBoxRect,
  pillTextColor,
  smoothRate,
  stateChipText,
} from './live-overlay';

type LiveState = 'idle' | 'camera' | 'starting' | 'running';

const NOT_READY_RETRY_MS = 200;
const NOT_READY_MAX_RETRIES = 25;
const SERVER_MESSAGE_CODES: ReadonlySet<string> = new Set(['INVALID_REQUEST', 'UNEXPECTED_RESPONSE']);

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Live multi-face view: boxes over every face in the camera, labelled with the recognized name.
 * Frames are sent strictly one at a time (capture, POST, await, draw, pause, repeat).
 */
@Component({
  selector: 'app-live',
  imports: [CameraSelectComponent, IconComponent],
  providers: [CameraService],
  templateUrl: './live.component.html',
})
export class LiveComponent implements OnInit, AfterViewInit, OnDestroy {
  private readonly api = inject(ApiService);
  protected readonly camera = inject(CameraService);

  private readonly stage = viewChild.required<ElementRef<HTMLDivElement>>('stage');
  private readonly video = viewChild.required<ElementRef<HTMLVideoElement>>('video');
  private readonly overlay = viewChild.required<ElementRef<HTMLCanvasElement>>('overlay');

  protected readonly state = signal<LiveState>('idle');
  protected readonly faces = signal<LiveFace[]>([]);
  protected readonly fps = signal<number | null>(null);
  protected readonly serverMs = signal<number | null>(null);
  protected readonly error = signal<{ code: string; message: string } | null>(null);

  protected readonly busy = computed(() => this.state() !== 'idle');
  protected readonly running = computed(() => this.state() === 'running');

  protected readonly faceRows = computed(() =>
    this.faces().map((f) => ({
      id: f.track_id,
      title: f.state === 'KNOWN' ? f.name || f.label || 'Known' : f.label || stateChipText(f.state),
      similarity: f.state === 'KNOWN' ? formatSimilarity(f.similarity) : null,
      chip: stateChipText(f.state),
      tone: faceStyle(f).tone,
    })),
  );

  private runId = 0;
  private liveId: string | null = null;
  private lastResponseAt: number | null = null;
  private resizeObserver: ResizeObserver | null = null;

  ngOnInit(): void {
    void this.camera.refreshDevices();
  }

  ngAfterViewInit(): void {
    if (typeof ResizeObserver === 'undefined') return;
    this.resizeObserver = new ResizeObserver(() => this.draw());
    this.resizeObserver.observe(this.stage().nativeElement);
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.stop();
  }

  protected async start(): Promise<void> {
    if (this.busy()) return;
    const id = ++this.runId;
    const cancelled = () => id !== this.runId;
    this.error.set(null);
    this.resetView();

    try {
      this.state.set('camera');
      await this.camera.start(this.video().nativeElement);
      if (cancelled()) return;

      this.state.set('starting');
      const liveId = await this.openSession();
      if (cancelled()) {
        this.closeSession(liveId);
        return;
      }
      this.state.set('running');

      let frameNumber = 0;
      let invalidStreak = 0;
      let notReady = 0;
      let restarted = false;

      while (!cancelled()) {
        if (this.camera.disconnected()) throw new CameraError('DISCONNECTED', cameraErrorMessage('DISCONNECTED'));

        let image: string;
        try {
          image = this.camera.captureFrame();
          notReady = 0;
        } catch (err) {
          if (err instanceof CameraError && err.code === 'VIDEO_NOT_READY' && ++notReady <= NOT_READY_MAX_RETRIES) {
            await sleep(NOT_READY_RETRY_MS);
            continue;
          }
          throw err;
        }

        const currentId = this.liveId;
        if (!currentId) return;
        try {
          const res = await this.api.liveFrame({ live_id: currentId, frame_number: frameNumber++, image_base64: image });
          if (cancelled()) return;
          invalidStreak = 0;
          restarted = false;
          this.onFrame(res.faces, res.face_count, res.timings_ms?.total ?? null);
        } catch (err) {
          if (cancelled()) return;
          const apiErr = toApiError(err);
          if (apiErr.code === 'SESSION_NOT_FOUND' && !restarted) {
            // Session idled out server-side: open a fresh one transparently (once per failure).
            restarted = true;
            this.liveId = null;
            await this.openSession();
            if (cancelled()) return;
            frameNumber = 0;
            continue;
          }
          if (apiErr.code !== 'INVALID_FRAME' || ++invalidStreak >= MAX_CONSECUTIVE_INVALID_FRAMES) throw apiErr;
        }

        await sleep(LIVE_FRAME_DELAY_MS);
      }
    } catch (err) {
      if (cancelled()) return;
      this.error.set(this.toError(err));
      this.stop();
    }
  }

  /** Stops the loop and camera, closes the server session (best-effort) and clears the overlay. */
  protected stop(): void {
    this.runId++;
    this.camera.stop();
    if (this.liveId) this.closeSession(this.liveId);
    this.liveId = null;
    this.state.set('idle');
    this.resetView();
  }

  private async openSession(): Promise<string> {
    const { live_id } = await this.api.liveStart();
    this.liveId = live_id;
    return live_id;
  }

  private closeSession(liveId: string): void {
    this.api.liveStop(liveId).catch(() => undefined);
  }

  private onFrame(faces: LiveFace[], faceCount: number, totalMs: number | null): void {
    const now = performance.now();
    if (this.lastResponseAt != null) this.fps.set(smoothRate(this.fps(), now - this.lastResponseAt));
    this.lastResponseAt = now;
    this.serverMs.set(typeof totalMs === 'number' ? totalMs : null);
    this.faces.set(faceCount > 0 ? faces : []);
    this.draw();
  }

  private resetView(): void {
    this.faces.set([]);
    this.fps.set(null);
    this.serverMs.set(null);
    this.lastResponseAt = null;
    this.draw();
  }

  /** Redraws all boxes on the overlay canvas (sized to the stage, DPR-aware, text un-mirrored). */
  private draw(): void {
    const canvas = this.overlay()?.nativeElement;
    const stage = this.stage()?.nativeElement;
    if (!canvas || !stage) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const cssW = stage.clientWidth;
    const cssH = stage.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    const pxW = Math.max(1, Math.round(cssW * dpr));
    const pxH = Math.max(1, Math.round(cssH * dpr));
    if (canvas.width !== pxW) canvas.width = pxW;
    if (canvas.height !== pxH) canvas.height = pxH;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const faces = this.faces();
    if (!faces.length || !this.camera.active()) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const video = this.video().nativeElement;
    const rect = drawnVideoRect(cssW, cssH, video.videoWidth, video.videoHeight, 'cover');
    const css = getComputedStyle(stage);
    const font = css.getPropertyValue('--font').trim() || 'system-ui, sans-serif';
    const fallbackColor = '#71717a';

    for (const face of faces) {
      const style = faceStyle(face);
      const color = css.getPropertyValue(style.colorVar).trim() || fallbackColor;
      const box = mirroredBoxRect(face.bbox, rect, cssW);
      if (box.width < 1 || box.height < 1) continue;

      // Box
      ctx.save();
      ctx.lineWidth = 2;
      ctx.strokeStyle = color;
      ctx.setLineDash(style.dashed ? [6, 4] : []);
      ctx.beginPath();
      ctx.roundRect(box.x, box.y, box.width, box.height, 6);
      ctx.stroke();
      ctx.restore();

      // Label pill (above the box, or just inside it when there is no room)
      const padX = 7;
      const pillH = 20;
      ctx.font = `600 12px ${font}`;
      const mainW = ctx.measureText(style.text).width;
      let detailW = 0;
      if (style.detail) {
        ctx.font = `500 11px ${font}`;
        detailW = ctx.measureText(style.detail).width + 6;
      }
      const pillW = Math.min(mainW + detailW + padX * 2, Math.max(cssW - 4, 40));
      let px = box.x;
      px = Math.max(2, Math.min(px, cssW - pillW - 2));
      let py = box.y - pillH - 4;
      if (py < 2) py = box.y + 4;

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(px, py, pillW, pillH, 6);
      ctx.fill();

      const textColor = pillTextColor(color);
      ctx.save();
      ctx.beginPath();
      ctx.rect(px, py, pillW, pillH);
      ctx.clip();
      ctx.fillStyle = textColor;
      ctx.textBaseline = 'middle';
      ctx.font = `600 12px ${font}`;
      ctx.fillText(style.text, px + padX, py + pillH / 2 + 0.5);
      if (style.detail) {
        ctx.globalAlpha = 0.8;
        ctx.font = `500 11px ${font}`;
        ctx.fillText(style.detail, px + padX + mainW + 6, py + pillH / 2 + 0.5);
      }
      ctx.restore();
    }
  }

  private toError(err: unknown): { code: string; message: string } {
    if (err instanceof CameraError) return { code: err.code, message: err.message };
    const e = toApiError(err);
    if (e.code === 'SESSION_STATE') {
      return { code: e.code, message: 'Too many live sessions are running on the server. Close other Live tabs and try again.' };
    }
    if (e.code === 'SESSION_NOT_FOUND') {
      return { code: e.code, message: 'The live session was lost on the server and could not be restarted.' };
    }
    const message = SERVER_MESSAGE_CODES.has(e.code) ? e.message : errorCodeText(e.code, e.message);
    return { code: e.code, message };
  }

}

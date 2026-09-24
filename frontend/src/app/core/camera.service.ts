import { Injectable, OnDestroy, signal } from '@angular/core';

import { CameraError, cameraErrorMessage, toCameraError } from './camera-errors';
import { CAPTURE_MAX_HEIGHT, CAPTURE_MAX_WIDTH, JPEG_QUALITY } from './config';

export interface CameraDevice {
  deviceId: string;
  label: string;
}

/**
 * Wraps getUserMedia, device enumeration and frame capture.
 * Provided per page component so each page owns (and releases) its own stream.
 */
@Injectable()
export class CameraService implements OnDestroy {
  readonly devices = signal<CameraDevice[]>([]);
  readonly selectedDeviceId = signal<string>('');
  readonly active = signal(false);
  /** Set when the live track ends unexpectedly (unplugged, revoked, taken by the OS). */
  readonly disconnected = signal(false);

  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private readonly onTrackEnded = () => {
    this.disconnected.set(true);
    this.stop();
  };

  isSupported(): boolean {
    return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  }

  /** Lists video inputs. Labels are only filled in after permission has been granted. */
  async refreshDevices(): Promise<void> {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const cams = all
        .filter((d) => d.kind === 'videoinput')
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Camera ${i + 1}` }));
      this.devices.set(cams);
      const current = this.selectedDeviceId();
      if (current && !cams.some((c) => c.deviceId === current)) this.selectedDeviceId.set('');
    } catch {
      this.devices.set([]);
    }
  }

  /** Starts the camera into the given video element. Rejects with CameraError. */
  async start(video: HTMLVideoElement): Promise<void> {
    if (!this.isSupported()) throw new CameraError('UNSUPPORTED', cameraErrorMessage('UNSUPPORTED'));
    this.stop();
    this.disconnected.set(false);

    const deviceId = this.selectedDeviceId();
    const constraints: MediaStreamConstraints = {
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: 640, height: 480 }
        : { width: 640, height: 480, facingMode: 'user' },
      audio: false,
    };

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      throw toCameraError(err);
    }

    this.stream = stream;
    this.video = video;
    for (const track of stream.getVideoTracks()) track.addEventListener('ended', this.onTrackEnded);

    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    try {
      await video.play();
    } catch (err) {
      this.stop();
      throw toCameraError(err);
    }
    await this.waitForVideo(video);
    this.active.set(true);

    const settingsId = stream.getVideoTracks()[0]?.getSettings().deviceId;
    await this.refreshDevices();
    if (settingsId && !this.selectedDeviceId()) this.selectedDeviceId.set(settingsId);
  }

  /** Stops all tracks and detaches the stream. Safe to call repeatedly. */
  stop(): void {
    if (this.stream) {
      for (const track of this.stream.getTracks()) {
        track.removeEventListener('ended', this.onTrackEnded);
        track.stop();
      }
    }
    if (this.video) this.video.srcObject = null;
    this.stream = null;
    this.video = null;
    this.active.set(false);
  }

  /**
   * Captures the current RAW (un-mirrored) frame as a JPEG data URL, scaled to fit 640x480.
   * The <video> is only mirrored with CSS; the canvas draw is not flipped.
   */
  captureFrame(): string {
    const video = this.video;
    if (!video || !this.stream || this.disconnected()) {
      throw new CameraError('DISCONNECTED', cameraErrorMessage('DISCONNECTED'));
    }
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      throw new CameraError('VIDEO_NOT_READY', cameraErrorMessage('VIDEO_NOT_READY'));
    }
    const scale = Math.min(1, CAPTURE_MAX_WIDTH / w, CAPTURE_MAX_HEIGHT / h);
    const cw = Math.round(w * scale);
    const ch = Math.round(h * scale);

    try {
      const canvas = (this.canvas ??= document.createElement('canvas'));
      if (canvas.width !== cw) canvas.width = cw;
      if (canvas.height !== ch) canvas.height = ch;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('2D context unavailable');
      ctx.drawImage(video, 0, 0, cw, ch);
      const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
      if (!dataUrl.startsWith('data:image/') || dataUrl.length < 200) throw new Error('empty frame');
      return dataUrl;
    } catch {
      throw new CameraError('CAPTURE_FAILED', cameraErrorMessage('CAPTURE_FAILED'));
    }
  }

  ngOnDestroy(): void {
    this.stop();
  }

  private waitForVideo(video: HTMLVideoElement, timeoutMs = 5000): Promise<void> {
    if (video.videoWidth > 0) return Promise.resolve();
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer);
        video.removeEventListener('loadeddata', done);
        resolve();
      };
      const timer = setTimeout(done, timeoutMs); // capture handles a still-unready video
      video.addEventListener('loadeddata', done);
    });
  }
}

import { Component, ElementRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { DecimalPipe } from '@angular/common';

import { ApiService } from '../../core/api.service';
import { RecognitionResult } from '../../core/api.types';
import { CameraService } from '../../core/camera.service';
import { RecognitionOutcome, errorCodeText, recognitionOutcome } from '../../core/messages';
import { SessionOutcome, SessionRunner } from '../../core/session-runner.service';
import { CameraSelectComponent } from '../../shared/camera-select.component';
import { IconComponent, IconName } from '../../shared/icon.component';
import { LiveStatusComponent } from '../../shared/live-status.component';

@Component({
  selector: 'app-recognize',
  imports: [DecimalPipe, LiveStatusComponent, CameraSelectComponent, IconComponent],
  providers: [CameraService, SessionRunner],
  templateUrl: './recognize.component.html',
})
export class RecognizeComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly camera = inject(CameraService);
  protected readonly runner = inject(SessionRunner);

  private readonly video = viewChild.required<ElementRef<HTMLVideoElement>>('video');

  protected readonly outcome = signal<SessionOutcome<RecognitionResult> | null>(null);

  /** Card for the final result; errors that correspond to a result kind reuse that card. */
  protected readonly card = computed<RecognitionOutcome | null>(() => {
    const o = this.outcome();
    if (!o) return null;
    if (o.kind === 'completed') return recognitionOutcome(o.result);
    if (o.code === 'SESSION_EXPIRED') return recognitionOutcome({ result: 'EXPIRED' });
    return {
      title: 'ERROR',
      tone: 'danger',
      detail: o.message || errorCodeText(o.code),
      person: null,
      similarity: null,
    };
  });

  /** Visual state of the camera frame (border glow / scanning ring). Presentation only. */
  protected readonly stageState = computed<'idle' | 'live' | 'scanning' | 'success' | 'warn' | 'failure'>(() => {
    const c = this.card();
    if (c) return c.tone === 'success' ? 'success' : c.tone === 'neutral' ? 'warn' : 'failure';
    const s = this.runner.state();
    if (s === 'running' || s === 'completing') return 'scanning';
    return this.runner.busy() ? 'live' : 'idle';
  });

  protected readonly resultIcon = computed<IconName>(() => {
    switch (this.card()?.title) {
      case 'KNOWN PERSON': return 'check';
      case 'UNKNOWN PERSON': return 'question';
      case 'LIVENESS FAILED': return 'x';
      case 'CHALLENGE FAILED': return 'move';
      case 'MULTIPLE FACES': return 'users';
      case 'SESSION EXPIRED': return 'clock';
      default: return 'alert';
    }
  });

  /** Similarity as a 0..100 bar width (clamped). */
  protected readonly similarityPct = computed(() => {
    const s = this.card()?.similarity;
    return s == null ? 0 : Math.round(Math.min(1, Math.max(0, s)) * 100);
  });

  ngOnInit(): void {
    void this.camera.refreshDevices();
  }

  protected async start(): Promise<void> {
    if (this.runner.busy()) return;
    this.outcome.set(null);
    const outcome = await this.runner.run<RecognitionResult>(this.video().nativeElement, {
      start: () => this.api.startRecognition(),
      frame: (req) => this.api.recognitionFrame(req),
      complete: (id) => this.api.completeRecognition(id),
    });
    if (outcome) this.outcome.set(outcome);
  }

  protected cancel(): void {
    this.runner.cancel();
  }
}

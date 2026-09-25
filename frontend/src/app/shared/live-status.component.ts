import { Component, computed, input } from '@angular/core';

import { SessionView } from '../core/api.types';
import { LiveStatus } from '../core/messages';
import { RunnerState } from '../core/session-runner.service';
import { IconComponent, IconName } from './icon.component';

const QUALITY_ICON: Record<string, IconName> = {
  FACE_TOO_SMALL: 'frame',
  TOO_DARK: 'sun',
  TOO_BRIGHT: 'moon',
  TOO_BLURRY: 'hand',
  NOT_FRONTAL: 'eye',
  LOW_CONTRAST: 'sun',
  LOW_DETECTION_CONFIDENCE: 'eye',
  LANDMARKS_OUTSIDE_FACE: 'frame',
};

/** Live status text, big instruction, quality hint and progress meters shown while a session runs. */
@Component({
  selector: 'app-live-status',
  imports: [IconComponent],
  template: `
    <div class="live-status" aria-live="polite" aria-atomic="false">
      @switch (state()) {
        @case ('camera') { <div class="step-row"><span class="spinner" aria-hidden="true"></span><p class="status-text">Starting camera...</p></div> }
        @case ('starting') { <div class="step-row"><span class="spinner" aria-hidden="true"></span><p class="status-text">Starting session...</p></div> }
        @case ('completing') { <div class="step-row"><span class="spinner" aria-hidden="true"></span><p class="status-text">Finishing...</p></div> }
        @case ('running') {
          @if (status().instruction) {
            <p class="instruction">{{ status().instruction }}</p>
          }
          <div class="hint" [class.warning]="status().warning">
            <span class="hint-icon"><app-icon [name]="hintIcon()" /></span>
            <span class="status-text-inline">{{ status().text }}</span>
          </div>

          @if (passive(); as p) {
            <div class="meter">
              <div class="meter-head">
                <span class="meter-label" [class.done]="p.done">
                  <app-icon [name]="p.done ? 'check-circle' : 'shield'" /> Liveness frames
                </span>
                <b>{{ p.value }}/{{ p.max }}</b>
              </div>
              <div class="progress" [class.active]="!p.done" [class.done]="p.done"
                   role="progressbar" aria-label="Liveness frames" [attr.aria-valuenow]="p.value" aria-valuemin="0" [attr.aria-valuemax]="p.max">
                <div class="progress-fill" [style.width.%]="p.pct"></div>
              </div>
            </div>
          }

          @if (actions(); as a) {
            <div class="meter">
              <div class="meter-head">
                <span class="meter-label" [class.done]="a.done">
                  <app-icon [name]="a.done ? 'check-circle' : 'move'" /> Head-movement challenge
                </span>
                <b>{{ a.value }}/{{ a.max }}</b>
              </div>
              <div class="dots" role="progressbar" aria-label="Challenge actions completed"
                   [attr.aria-valuenow]="a.value" aria-valuemin="0" [attr.aria-valuemax]="a.max">
                @for (i of a.steps; track i) {
                  <span [class.on]="i < a.value" [class.cur]="i === a.value"></span>
                }
              </div>
            </div>
          }

          @if (!passive() && !actions() && status().progress !== null) {
            <div class="meter">
              <div class="meter-head"><span class="meter-label">{{ status().progressLabel }}</span><b>{{ progressPct() }}%</b></div>
              <div class="progress active" role="progressbar" [attr.aria-valuenow]="progressPct()" aria-valuemin="0" aria-valuemax="100">
                <div class="progress-fill" [style.width.%]="progressPct()"></div>
              </div>
            </div>
          }
        }
      }
    </div>
  `,
})
export class LiveStatusComponent {
  readonly state = input.required<RunnerState>();
  readonly status = input.required<LiveStatus>();
  /** Latest session view (optional); enables the separate liveness / challenge meters. */
  readonly view = input<SessionView | null>(null);

  protected progressPct(): number {
    return Math.round((this.status().progress ?? 0) * 100);
  }

  protected readonly passive = computed(() => {
    const v = this.view();
    if (!v || v.passive_frames_required <= 0) return null;
    const value = Math.min(v.passive_frames, v.passive_frames_required);
    const max = v.passive_frames_required;
    return { value, max, pct: Math.round((value / max) * 100), done: value >= max || v.phase !== 'PASSIVE' };
  });

  protected readonly actions = computed(() => {
    const v = this.view();
    if (!v || v.total_actions <= 0 || v.phase === 'PASSIVE') return null;
    const value = Math.min(v.completed_actions, v.total_actions);
    return {
      value,
      max: v.total_actions,
      done: value >= v.total_actions,
      steps: Array.from({ length: v.total_actions }, (_, i) => i),
    };
  });

  protected readonly hintIcon = computed<IconName>(() => {
    const v = this.view();
    const frame = v?.frame;
    if (frame?.frame_error === 'NO_FACE') return 'frame';
    if (frame?.frame_error === 'MULTIPLE_FACES') return 'users';
    if (frame?.frame_error === 'LOW_FACE_QUALITY') {
      return QUALITY_ICON[frame.quality?.quality_reason ?? ''] ?? 'alert';
    }
    if (this.status().warning) return 'alert';
    if (v?.phase === 'ACTIVE') return 'move';
    if (v?.phase === 'PASSIVE') return 'shield';
    return 'sparkle';
  });
}

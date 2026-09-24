import { Component, input } from '@angular/core';

import { LiveStatus } from '../core/messages';
import { RunnerState } from '../core/session-runner.service';

/** Live status text, big instruction and progress bar shown while a session runs. */
@Component({
  selector: 'app-live-status',
  template: `
    <div class="live-status" aria-live="polite">
      @switch (state()) {
        @case ('camera') { <p class="status-text">Starting camera...</p> }
        @case ('starting') { <p class="status-text">Starting session...</p> }
        @case ('completing') { <p class="status-text">Finishing...</p> }
        @case ('running') {
          @if (status().instruction) {
            <p class="instruction">{{ status().instruction }}</p>
          }
          <p class="status-text" [class.warning]="status().warning">{{ status().text }}</p>
          @if (status().progress !== null) {
            <div class="progress" role="progressbar" [attr.aria-valuenow]="progressPct()" aria-valuemin="0" aria-valuemax="100">
              <div class="progress-fill" [style.width.%]="progressPct()"></div>
            </div>
            <p class="muted small">{{ status().progressLabel }}</p>
          }
        }
      }
    </div>
  `,
})
export class LiveStatusComponent {
  readonly state = input.required<RunnerState>();
  readonly status = input.required<LiveStatus>();

  protected progressPct(): number {
    return Math.round((this.status().progress ?? 0) * 100);
  }
}

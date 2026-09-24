import { Component, OnInit, inject } from '@angular/core';

import { HealthService } from '../core/health.service';

@Component({
  selector: 'app-status-bar',
  template: `
    <div class="status-bar">
      <span>
        Backend:
        @if (health.health(); as h) {
          <b [class.ok]="h.status === 'ok'" [class.bad]="h.status !== 'ok'">{{ h.status }}</b>
          · DB <b [class.ok]="h.database_ok" [class.bad]="!h.database_ok">{{ h.database_ok ? 'ok' : 'down' }}</b>
        } @else if (health.error()) {
          <b class="bad">unreachable</b>
        } @else {
          <b>checking...</b>
        }
      </span>
      <span>
        Models:
        @if (health.models(); as m) {
          <b [class.ok]="m.calibrated" [class.warn]="!m.calibrated">{{ m.calibrated ? 'calibrated' : 'not calibrated' }}</b>
        } @else {
          <b>-</b>
        }
      </span>
      <button type="button" class="link" (click)="health.refresh()">Refresh</button>
    </div>

    @if (health.error() && !health.health()) {
      <div class="banner banner-danger">{{ health.error() }}</div>
    }
    @if (health.health()?.database_ok === false) {
      <div class="banner banner-danger">The backend database is not available (database_ok = false). Enrollment and recognition will fail.</div>
    }
    @if (health.models()?.calibrated === false) {
      <div class="banner banner-warn">
        Models are not calibrated (no identity threshold). Recognition results are not meaningful until calibration has been run.
      </div>
    }
  `,
})
export class StatusBarComponent implements OnInit {
  protected readonly health = inject(HealthService);

  ngOnInit(): void {
    this.health.startPolling();
  }
}

import { Component, OnInit, inject } from '@angular/core';

import { HealthService } from '../core/health.service';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-status-bar',
  imports: [IconComponent],
  template: `
    <div class="status-bar" role="status" aria-label="Backend status">
      @if (health.health(); as h) {
        <span class="chip">
          <span class="dot" [class.ok]="h.status === 'ok'" [class.bad]="h.status !== 'ok'"></span>
          Backend <b>{{ h.status }}</b>
        </span>
        <span class="chip">
          <span class="dot" [class.ok]="h.database_ok" [class.bad]="!h.database_ok"></span>
          DB <b>{{ h.database_ok ? 'ok' : 'down' }}</b>
        </span>
      } @else if (health.error()) {
        <span class="chip">
          <span class="dot bad"></span>
          Backend <b>unreachable</b>
        </span>
      } @else {
        <span class="chip">
          <span class="dot pending"></span>
          Backend <b>checking...</b>
        </span>
      }
      <span class="chip">
        @if (health.models(); as m) {
          <span class="dot" [class.ok]="m.calibrated" [class.warn]="!m.calibrated"></span>
          Models <b>{{ m.calibrated ? 'calibrated' : 'not calibrated' }}</b>
        } @else {
          <span class="dot"></span>
          Models <b>-</b>
        }
      </span>
      <button type="button" class="chip-button" (click)="health.refresh()" aria-label="Refresh backend status">
        <app-icon name="refresh" /> Refresh
      </button>
    </div>

    @if ((health.error() && !health.health()) || health.health()?.database_ok === false || health.models()?.calibrated === false) {
      <div class="banners">
        @if (health.error() && !health.health()) {
          <div class="banner banner-danger" role="alert"><app-icon name="alert" /><span>{{ health.error() }}</span></div>
        }
        @if (health.health()?.database_ok === false) {
          <div class="banner banner-danger" role="alert">
            <app-icon name="alert" />
            <span>The backend database is not available (database_ok = false). Enrollment and recognition will fail.</span>
          </div>
        }
        @if (health.models()?.calibrated === false) {
          <div class="banner banner-warn">
            <app-icon name="info" />
            <span>Models are not calibrated (no identity threshold). Recognition results are not meaningful until calibration has been run.</span>
          </div>
        }
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

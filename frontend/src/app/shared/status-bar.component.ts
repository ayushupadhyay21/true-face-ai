import { Component, OnInit, inject } from '@angular/core';

import { HealthService } from '../core/health.service';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-status-bar',
  imports: [IconComponent],
  template: `
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

import { Component, input } from '@angular/core';

import { CameraService } from '../core/camera.service';

/** Camera dropdown, shown only when more than one video input exists. */
@Component({
  selector: 'app-camera-select',
  template: `
    @if (camera().devices().length > 1) {
      <label class="field inline">
        <span>Camera</span>
        <select
          [disabled]="disabled()"
          [value]="camera().selectedDeviceId()"
          (change)="onChange($event)"
        >
          <option value="">Default (front camera)</option>
          @for (d of camera().devices(); track d.deviceId) {
            <option [value]="d.deviceId">{{ d.label }}</option>
          }
        </select>
      </label>
    }
  `,
})
export class CameraSelectComponent {
  readonly camera = input.required<CameraService>();
  readonly disabled = input(false);

  protected onChange(event: Event): void {
    this.camera().selectedDeviceId.set((event.target as HTMLSelectElement).value);
  }
}

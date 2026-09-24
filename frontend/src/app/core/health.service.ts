import { Injectable, inject, signal } from '@angular/core';

import { toApiError } from './api-error';
import { HealthData, ModelsHealthData } from './api.types';
import { ApiService } from './api.service';
import { HEALTH_POLL_MS } from './config';

/** Polls /health and /health/models for the status bar and warning banners. */
@Injectable({ providedIn: 'root' })
export class HealthService {
  private readonly api = inject(ApiService);

  readonly health = signal<HealthData | null>(null);
  readonly models = signal<ModelsHealthData | null>(null);
  readonly error = signal<string | null>(null);
  readonly checkedAt = signal<Date | null>(null);

  private timer: ReturnType<typeof setInterval> | null = null;

  startPolling(): void {
    if (this.timer) return;
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(), HEALTH_POLL_MS);
  }

  async refresh(): Promise<void> {
    const [h, m] = await Promise.allSettled([this.api.health(), this.api.modelsHealth()]);
    this.health.set(h.status === 'fulfilled' ? h.value : null);
    this.models.set(m.status === 'fulfilled' ? m.value : null);
    const failed = h.status === 'rejected' ? h.reason : m.status === 'rejected' ? m.reason : null;
    this.error.set(failed ? toApiError(failed).message : null);
    this.checkedAt.set(new Date());
  }
}

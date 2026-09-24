import { Component, ElementRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { EnrollmentResult, Person } from '../../core/api.types';
import { CameraService } from '../../core/camera.service';
import { errorCodeText, formatPoses } from '../../core/messages';
import { SessionOutcome, SessionRunner } from '../../core/session-runner.service';
import { CameraSelectComponent } from '../../shared/camera-select.component';
import { LiveStatusComponent } from '../../shared/live-status.component';

@Component({
  selector: 'app-enroll',
  imports: [ReactiveFormsModule, LiveStatusComponent, CameraSelectComponent],
  providers: [CameraService, SessionRunner],
  templateUrl: './enroll.component.html',
})
export class EnrollComponent implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly camera = inject(CameraService);
  protected readonly runner = inject(SessionRunner);

  private readonly video = viewChild.required<ElementRef<HTMLVideoElement>>('video');

  protected readonly form = new FormGroup({
    name: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(200)] }),
    externalId: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(200)] }),
  });

  protected readonly outcome = signal<SessionOutcome<EnrollmentResult> | null>(null);
  protected readonly person = signal<Person | null>(null);
  protected readonly enrolled = computed(() => {
    const o = this.outcome();
    return o?.kind === 'completed' && o.result.result === 'ENROLLED';
  });
  protected readonly errorCodeText = errorCodeText;
  protected readonly formatPoses = formatPoses;

  ngOnInit(): void {
    void this.camera.refreshDevices();
  }

  protected async start(): Promise<void> {
    if (this.form.invalid || this.runner.busy()) {
      this.form.markAllAsTouched();
      return;
    }
    const name = this.form.controls.name.value.trim();
    const externalId = this.form.controls.externalId.value.trim();
    if (!name) {
      this.form.controls.name.setErrors({ required: true });
      return;
    }
    this.outcome.set(null);

    const outcome = await this.runner.run<EnrollmentResult>(this.video().nativeElement, {
      start: async () => {
        // Reuse the person created by a previous failed attempt with the same details.
        let person = this.person();
        if (!person || person.name !== name || (person.external_id ?? '') !== externalId) {
          person = await this.api.createPerson({ name, ...(externalId ? { external_id: externalId } : {}) });
          this.person.set(person);
        }
        return this.api.startEnrollment(person.id);
      },
      frame: (req) => this.api.enrollmentFrame(req),
      complete: (id) => this.api.completeEnrollment(id),
    });
    if (outcome) this.outcome.set(outcome);
  }

  protected cancel(): void {
    this.runner.cancel();
  }

  protected newEnrollment(): void {
    this.runner.reset();
    this.outcome.set(null);
    this.person.set(null);
    this.form.reset();
  }
}

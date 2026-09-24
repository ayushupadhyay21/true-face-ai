import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, firstValueFrom, map, throwError } from 'rxjs';

import { toApiError, unwrapEnvelope } from './api-error';
import {
  EnrollmentResult,
  Envelope,
  FrameRequest,
  HealthData,
  ModelsHealthData,
  Person,
  PersonCreateRequest,
  RecognitionResult,
  SessionView,
} from './api.types';
import { API_BASE_URL } from './config';

/** Typed wrapper around the backend API. All methods reject with ApiError on failure. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  health(): Promise<HealthData> {
    return this.get<HealthData>('/health');
  }

  modelsHealth(): Promise<ModelsHealthData> {
    return this.get<ModelsHealthData>('/health/models');
  }

  createPerson(body: PersonCreateRequest): Promise<Person> {
    return this.post<Person>('/api/person', body);
  }

  startEnrollment(personId: string): Promise<SessionView> {
    return this.post<SessionView>('/api/enrollment/start', { person_id: personId });
  }

  enrollmentFrame(body: FrameRequest): Promise<SessionView> {
    return this.post<SessionView>('/api/enrollment/frame', body);
  }

  completeEnrollment(sessionId: string): Promise<EnrollmentResult> {
    return this.post<EnrollmentResult>('/api/enrollment/complete', { session_id: sessionId });
  }

  startRecognition(): Promise<SessionView> {
    return this.post<SessionView>('/api/recognition/start', null);
  }

  recognitionFrame(body: FrameRequest): Promise<SessionView> {
    return this.post<SessionView>('/api/recognition/frame', body);
  }

  completeRecognition(sessionId: string): Promise<RecognitionResult> {
    return this.post<RecognitionResult>('/api/recognition/complete', { session_id: sessionId });
  }

  private get<T>(path: string): Promise<T> {
    return this.unwrap<T>(this.http.get<Envelope<T>>(API_BASE_URL + path));
  }

  private post<T>(path: string, body: unknown): Promise<T> {
    return this.unwrap<T>(this.http.post<Envelope<T>>(API_BASE_URL + path, body));
  }

  private unwrap<T>(obs: Observable<Envelope<T>>): Promise<T> {
    return firstValueFrom(
      obs.pipe(
        catchError((err: unknown) => throwError(() => toApiError(err))),
        map((body) => unwrapEnvelope<T>(body)),
      ),
    );
  }
}

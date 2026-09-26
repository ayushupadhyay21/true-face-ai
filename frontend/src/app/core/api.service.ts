import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, firstValueFrom, map, throwError } from 'rxjs';

import { toApiError, unwrapEnvelope } from './api-error';
import {
  EnrollmentResult,
  Envelope,
  FrameRequest,
  HealthData,
  LiveFrameRequest,
  LiveFrameResult,
  LiveStartData,
  LiveStopResult,
  ModelsHealthData,
  Person,
  PersonAssignRequest,
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

  /** Lists people, optionally filtered by status (e.g. 'UNASSIGNED' for unnamed live-mode faces). */
  listPeople(status?: string): Promise<Person[]> {
    return this.get<Person[]>('/api/person', status ? { status } : undefined);
  }

  /** Names a previously UNASSIGNED person and flips them to ACTIVE. */
  assignPerson(personId: string, body: PersonAssignRequest): Promise<Person> {
    return this.patch<Person>(`/api/person/${personId}`, body);
  }

  /** URL of a person's snapshot image (set only for auto-bucketed UNASSIGNED people). */
  snapshotUrl(personId: string): string {
    return `${API_BASE_URL}/api/person/${personId}/snapshot`;
  }

  /** Deletes a person and all their stored embeddings (cascades server-side). */
  deletePerson(personId: string): Promise<{ deleted: string }> {
    return this.delete<{ deleted: string }>(`/api/person/${personId}`);
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

  liveStart(): Promise<LiveStartData> {
    return this.post<LiveStartData>('/api/live/start', null);
  }

  liveFrame(body: LiveFrameRequest): Promise<LiveFrameResult> {
    return this.post<LiveFrameResult>('/api/live/frame', body);
  }

  liveStop(liveId: string): Promise<LiveStopResult> {
    return this.post<LiveStopResult>('/api/live/stop', { live_id: liveId });
  }

  private get<T>(path: string, params?: Record<string, string>): Promise<T> {
    return this.unwrap<T>(this.http.get<Envelope<T>>(API_BASE_URL + path, { params }));
  }

  private post<T>(path: string, body: unknown): Promise<T> {
    return this.unwrap<T>(this.http.post<Envelope<T>>(API_BASE_URL + path, body));
  }

  private patch<T>(path: string, body: unknown): Promise<T> {
    return this.unwrap<T>(this.http.patch<Envelope<T>>(API_BASE_URL + path, body));
  }

  private delete<T>(path: string): Promise<T> {
    return this.unwrap<T>(this.http.delete<Envelope<T>>(API_BASE_URL + path));
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

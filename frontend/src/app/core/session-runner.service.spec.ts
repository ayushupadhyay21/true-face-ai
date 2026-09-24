import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';

import { ApiError } from './api-error';
import { FrameRequest, SessionView } from './api.types';
import { CameraService } from './camera.service';
import { SessionRunner } from './session-runner.service';

function view(status: SessionView['status']): SessionView {
  return {
    session_id: 's1',
    session_type: 'RECOGNITION',
    status,
    phase: 'PASSIVE',
    current_action: null,
    instruction: null,
    completed_actions: 0,
    total_actions: 3,
    passive_frames: 0,
    passive_frames_required: 8,
    expires_at: '',
    error_code: null,
    message: null,
  };
}

class FakeCamera {
  disconnected = signal(false);
  active = signal(false);
  stopped = 0;
  async start(): Promise<void> {
    this.active.set(true);
  }
  stop(): void {
    this.stopped++;
    this.active.set(false);
  }
  captureFrame(): string {
    return 'data:image/jpeg;base64,AAAA';
  }
}

const fakeVideo = {} as HTMLVideoElement;

describe('SessionRunner', () => {
  let runner: SessionRunner;
  let camera: FakeCamera;

  beforeEach(() => {
    camera = new FakeCamera();
    TestBed.configureTestingModule({ providers: [SessionRunner, { provide: CameraService, useValue: camera }] });
    runner = TestBed.inject(SessionRunner);
  });

  it('sends frames one at a time with increasing numbers and completes once when PASSED', async () => {
    const sent: number[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const statuses: SessionView['status'][] = ['IN_PROGRESS', 'IN_PROGRESS', 'PASSED'];
    const complete = vi.fn(async () => ({ result: 'UNKNOWN' }));

    const outcome = await runner.run(fakeVideo, {
      start: async () => view('CREATED'),
      frame: async (req: FrameRequest) => {
        inFlight++;
        maxInFlight = Math.max(maxInFlight, inFlight);
        sent.push(req.frame_number);
        await Promise.resolve();
        inFlight--;
        return view(statuses[sent.length - 1]);
      },
      complete,
    });

    expect(sent).toEqual([0, 1, 2]);
    expect(maxInFlight).toBe(1);
    expect(complete).toHaveBeenCalledTimes(1);
    expect(outcome).toEqual({ kind: 'completed', result: { result: 'UNKNOWN' } });
    expect(runner.state()).toBe('done');
    expect(camera.stopped).toBeGreaterThan(0);
  });

  it('stops without completing on SESSION_EXPIRED', async () => {
    const complete = vi.fn();
    const outcome = await runner.run(fakeVideo, {
      start: async () => view('CREATED'),
      frame: async () => {
        throw new ApiError('SESSION_EXPIRED', 'expired');
      },
      complete,
    });
    expect(complete).not.toHaveBeenCalled();
    expect(outcome?.kind === 'error' && outcome.code).toBe('SESSION_EXPIRED');
    expect(runner.state()).toBe('error');
  });

  it('skips INVALID_FRAME up to 5 consecutive times, then stops', async () => {
    let calls = 0;
    const outcome = await runner.run(fakeVideo, {
      start: async () => view('CREATED'),
      frame: async () => {
        calls++;
        throw new ApiError('INVALID_FRAME', 'bad');
      },
      complete: vi.fn(),
    });
    expect(calls).toBe(5);
    expect(outcome?.kind === 'error' && outcome.code).toBe('INVALID_FRAME');
  });

  it('stops with an error when the camera is disconnected', async () => {
    let calls = 0;
    const outcome = await runner.run(fakeVideo, {
      start: async () => view('CREATED'),
      frame: async () => {
        calls++;
        camera.disconnected.set(true);
        return view('IN_PROGRESS');
      },
      complete: vi.fn(),
    });
    expect(calls).toBe(1);
    expect(outcome?.kind === 'error' && outcome.code).toBe('DISCONNECTED');
  });
});

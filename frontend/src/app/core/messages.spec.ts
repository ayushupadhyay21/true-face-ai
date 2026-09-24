import { SessionView } from './api.types';
import { errorCodeText, formatPoses, liveStatus, qualityReasonText, recognitionOutcome } from './messages';

function view(partial: Partial<SessionView>): SessionView {
  return {
    session_id: 's1',
    session_type: 'RECOGNITION',
    status: 'IN_PROGRESS',
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
    ...partial,
  };
}

describe('qualityReasonText', () => {
  it('maps known reasons to friendly text', () => {
    expect(qualityReasonText('FACE_TOO_SMALL')).toBe('Move closer');
    expect(qualityReasonText('TOO_DARK')).toBe('More light needed');
    expect(qualityReasonText('TOO_BLURRY')).toBe('Hold still');
    expect(qualityReasonText('NOT_FRONTAL')).toBe('Face the camera');
  });
  it('falls back for unknown or missing reasons', () => {
    expect(qualityReasonText('SOMETHING_NEW')).toBe('something new');
    expect(qualityReasonText(null)).toBe('Adjust your position');
  });
});

describe('errorCodeText', () => {
  it('uses friendly text for known codes and the fallback otherwise', () => {
    expect(errorCodeText('SESSION_EXPIRED')).toContain('expired');
    expect(errorCodeText('WEIRD', 'server said so')).toBe('server said so');
  });
});

describe('liveStatus', () => {
  it('starts with "Detecting face..."', () => {
    expect(liveStatus(null).text).toBe('Detecting face...');
  });
  it('shows the quality reason for LOW_FACE_QUALITY frames', () => {
    const s = liveStatus(
      view({
        frame: {
          face_count: 1,
          frame_error: 'LOW_FACE_QUALITY',
          quality: { quality_reason: 'TOO_DARK' },
          liveness_frame_score: null,
          timings_ms: {},
        },
      }),
    );
    expect(s.text).toBe('Checking quality... More light needed');
    expect(s.warning).toBe(true);
  });
  it('shows passive liveness progress', () => {
    const s = liveStatus(
      view({
        passive_frames: 3,
        frame: { face_count: 1, frame_error: null, quality: null, liveness_frame_score: 0.9, timings_ms: {} },
      }),
    );
    expect(s.text).toBe('Checking liveness... (3/8)');
    expect(s.progress).toBeCloseTo(3 / 8);
  });
  it('shows the instruction and action progress during ACTIVE', () => {
    const s = liveStatus(
      view({ phase: 'ACTIVE', current_action: 'LOOK_LEFT', instruction: 'Turn your head to your LEFT', completed_actions: 1 }),
    );
    expect(s.instruction).toBe('Turn your head to your LEFT');
    expect(s.progress).toBeCloseTo(1 / 3);
  });
});

describe('recognitionOutcome', () => {
  it('shows the person for KNOWN', () => {
    const o = recognitionOutcome({ result: 'KNOWN', similarity: 0.71, person: { id: '1', name: 'Ada', external_id: 'E1' } });
    expect(o.title).toBe('KNOWN PERSON');
    expect(o.person).toEqual({ name: 'Ada', externalId: 'E1' });
    expect(o.similarity).toBe(0.71);
  });
  it('never exposes a name for LIVENESS_FAILED, even if one is present', () => {
    const o = recognitionOutcome({
      result: 'LIVENESS_FAILED',
      person: { id: '1', name: 'Ada', external_id: null },
      similarity: 0.9,
    });
    expect(o.title).toBe('LIVENESS FAILED');
    expect(o.person).toBeNull();
    expect(o.similarity).toBeNull();
  });
  it('maps EXPIRED and other results', () => {
    expect(recognitionOutcome({ result: 'EXPIRED' }).title).toBe('SESSION EXPIRED');
    expect(recognitionOutcome({ result: 'MULTIPLE_FACES' }).title).toBe('MULTIPLE FACES');
    expect(recognitionOutcome({ result: 'CHALLENGE_FAILED' }).title).toBe('CHALLENGE FAILED');
    expect(recognitionOutcome({ result: 'UNKNOWN', similarity: 0.2 }).title).toBe('UNKNOWN PERSON');
  });
});

describe('formatPoses', () => {
  it('formats lists and maps', () => {
    expect(formatPoses(['CENTER', 'LEFT'])).toBe('CENTER, LEFT');
    expect(formatPoses({ CENTER: 3 })).toBe('CENTER x3');
    expect(formatPoses(undefined)).toBe('-');
  });
});

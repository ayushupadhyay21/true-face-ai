import {
  PILL_TEXT_DARK,
  PILL_TEXT_LIGHT,
  drawnVideoRect,
  faceStyle,
  formatSimilarity,
  hexLuminance,
  mirroredBoxRect,
  pillTextColor,
  smoothRate,
  stateChipText,
} from './live-overlay';

describe('drawnVideoRect', () => {
  it('fills the element exactly when aspect ratios match', () => {
    expect(drawnVideoRect(800, 600, 640, 480, 'cover')).toEqual({ x: 0, y: 0, width: 800, height: 600 });
    expect(drawnVideoRect(800, 600, 640, 480, 'contain')).toEqual({ x: 0, y: 0, width: 800, height: 600 });
  });
  it('crops (negative offset) with cover', () => {
    // 16:9 video in a 4:3 box: scaled to height, overflows horizontally.
    const r = drawnVideoRect(400, 300, 1280, 720, 'cover');
    expect(r.height).toBeCloseTo(300);
    expect(r.width).toBeCloseTo(533.333, 2);
    expect(r.x).toBeCloseTo(-66.667, 2);
    expect(r.y).toBeCloseTo(0);
  });
  it('letterboxes with contain', () => {
    const r = drawnVideoRect(400, 300, 1280, 720, 'contain');
    expect(r.width).toBeCloseTo(400);
    expect(r.height).toBeCloseTo(225);
    expect(r.x).toBeCloseTo(0);
    expect(r.y).toBeCloseTo(37.5);
  });
  it('handles missing sizes', () => {
    expect(drawnVideoRect(0, 0, 640, 480)).toEqual({ x: 0, y: 0, width: 0, height: 0 });
    expect(drawnVideoRect(400, 300, 0, 0)).toEqual({ x: 0, y: 0, width: 400, height: 300 });
  });
});

describe('mirroredBoxRect', () => {
  const full = { x: 0, y: 0, width: 400, height: 300 };
  it('mirrors x: a face on the raw left appears on the displayed right', () => {
    const r = mirroredBoxRect([0.1, 0.2, 0.3, 0.6], full, 400);
    expect(r.x).toBeCloseTo((1 - 0.3) * 400);
    expect(r.x + r.width).toBeCloseTo((1 - 0.1) * 400);
    expect(r.y).toBeCloseTo(0.2 * 300);
    expect(r.height).toBeCloseTo(0.4 * 300);
  });
  it('accounts for the cover-crop offset', () => {
    const rect = drawnVideoRect(400, 300, 1280, 720, 'cover'); // x = -66.67, width = 533.33
    const r = mirroredBoxRect([0.5, 0, 0.75, 1], rect, 400);
    expect(r.x).toBeCloseTo(rect.x + 0.25 * rect.width);
    expect(r.width).toBeCloseTo(0.25 * rect.width);
  });
  it('clamps and normalizes the bbox', () => {
    const r = mirroredBoxRect([1.2, -0.1, 0.8, 0.5], full, 400);
    expect(r.x).toBeCloseTo(0);
    expect(r.width).toBeCloseTo(0.2 * 400);
    expect(r.y).toBeCloseTo(0);
    expect(r.height).toBeCloseTo(0.5 * 300);
  });
});

describe('faceStyle', () => {
  const base = { label: '', name: null, similarity: null };
  it('KNOWN: green with name and similarity', () => {
    const s = faceStyle({ ...base, state: 'KNOWN', name: 'Ada', similarity: 0.874 });
    expect(s).toEqual({ tone: 'known', colorVar: '--ok-solid', text: 'Ada', detail: '87%', dashed: false });
  });
  it('UNKNOWN: accent "Unknown"', () => {
    expect(faceStyle({ ...base, state: 'UNKNOWN', label: 'whatever' })).toMatchObject({ colorVar: '--accent', text: 'Unknown' });
  });
  it('UNASSIGNED: amber "Unnamed" (auto-bucketed, not yet named)', () => {
    expect(faceStyle({ ...base, state: 'UNASSIGNED', label: 'Unknown-a1b2c3d4' })).toMatchObject({
      tone: 'unassigned',
      colorVar: '--warn-solid',
      text: 'Unnamed',
    });
  });
  it('CHECKING / LIVE: neutral gray with the server label', () => {
    expect(faceStyle({ ...base, state: 'CHECKING', label: 'Checking liveness' })).toMatchObject({
      tone: 'neutral',
      colorVar: '--muted',
      text: 'Checking liveness',
    });
    expect(faceStyle({ ...base, state: 'LIVE' }).text).toBe('Live');
  });
  it('SPOOF: red "Spoof"', () => {
    expect(faceStyle({ ...base, state: 'SPOOF', name: 'Ada' })).toMatchObject({ colorVar: '--danger-solid', text: 'Spoof', detail: null });
  });
  it('TOO_SMALL: gray dashed "Move closer"', () => {
    expect(faceStyle({ ...base, state: 'TOO_SMALL' })).toMatchObject({ colorVar: '--muted', text: 'Move closer', dashed: true });
  });
});

describe('small helpers', () => {
  it('formatSimilarity', () => {
    expect(formatSimilarity(0.5)).toBe('50%');
    expect(formatSimilarity(1.4)).toBe('100%');
    expect(formatSimilarity(null)).toBeNull();
  });
  it('stateChipText', () => {
    expect(stateChipText('TOO_SMALL')).toBe('Too small');
    expect(stateChipText('CHECKING')).toBe('Checking');
    expect(stateChipText('UNASSIGNED')).toBe('Unnamed');
  });
  it('smoothRate', () => {
    expect(smoothRate(null, 100)).toBe(10);
    expect(smoothRate(10, 50, 0.5)).toBe(15);
    expect(smoothRate(7, 0)).toBe(7);
  });
  it('hexLuminance / pillTextColor', () => {
    expect(hexLuminance('#fff')).toBeCloseTo(1);
    expect(hexLuminance('#000000')).toBeCloseTo(0);
    expect(hexLuminance('rgb(0,0,0)')).toBeNull();
    expect(pillTextColor('#4f46e5')).toBe(PILL_TEXT_LIGHT);
    expect(pillTextColor('#22c55e')).toBe(PILL_TEXT_DARK);
    expect(pillTextColor('oklch(0.5 0.1 200)')).toBe(PILL_TEXT_LIGHT);
  });
});

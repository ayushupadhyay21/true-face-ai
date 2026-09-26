import { LiveFace, LiveFaceState } from '../../core/api.types';

/** Pure helpers for the Live page overlay (geometry, styling, stats). No DOM access. */

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type ObjectFit = 'cover' | 'contain';

/**
 * The rectangle (in element CSS pixels) where the video frame is actually painted inside an
 * element of size elW x elH, for the given object-fit. Centered, like the default object-position.
 * With `cover` the rect can extend past the element (it is cropped); with `contain` it is letterboxed.
 */
export function drawnVideoRect(elW: number, elH: number, vidW: number, vidH: number, fit: ObjectFit = 'cover'): Rect {
  if (!(elW > 0) || !(elH > 0)) return { x: 0, y: 0, width: 0, height: 0 };
  if (!(vidW > 0) || !(vidH > 0)) return { x: 0, y: 0, width: elW, height: elH };
  const scale = fit === 'cover' ? Math.max(elW / vidW, elH / vidH) : Math.min(elW / vidW, elH / vidH);
  const width = vidW * scale;
  const height = vidH * scale;
  return { x: (elW - width) / 2, y: (elH - height) / 2, width, height };
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/**
 * Maps a RAW (un-mirrored) normalized bbox [x1,y1,x2,y2] to element coordinates of a video that
 * is displayed mirrored with CSS `scaleX(-1)` around the element center.
 * `rect` is the drawn video rect before mirroring (see drawnVideoRect); `elW` the element width.
 * For a centered rect this is `rect.x + (1 - x2) * rect.width .. rect.x + (1 - x1) * rect.width`.
 */
export function mirroredBoxRect(bbox: readonly number[], rect: Rect, elW: number): Rect {
  const x1 = clamp01(Math.min(bbox[0], bbox[2]));
  const x2 = clamp01(Math.max(bbox[0], bbox[2]));
  const y1 = clamp01(Math.min(bbox[1], bbox[3]));
  const y2 = clamp01(Math.max(bbox[1], bbox[3]));
  const mirroredRectX = elW - rect.x - rect.width;
  return {
    x: mirroredRectX + (1 - x2) * rect.width,
    y: rect.y + y1 * rect.height,
    width: (x2 - x1) * rect.width,
    height: (y2 - y1) * rect.height,
  };
}

export type FaceTone = 'known' | 'unassigned' | 'unknown' | 'neutral' | 'spoof' | 'small';

export interface FaceStyle {
  tone: FaceTone;
  /** CSS custom property holding the box / pill color. */
  colorVar: string;
  /** Main pill text. */
  text: string;
  /** Secondary pill text (e.g. similarity "87%"), or null. */
  detail: string | null;
  dashed: boolean;
}

/** Visual style for a tracked face, by its server state. */
export function faceStyle(face: Pick<LiveFace, 'state' | 'label' | 'name' | 'similarity'>): FaceStyle {
  switch (face.state) {
    case 'KNOWN':
      return {
        tone: 'known',
        colorVar: '--ok-solid',
        text: face.name || face.label || 'Known',
        detail: formatSimilarity(face.similarity),
        dashed: false,
      };
    case 'UNASSIGNED':
      return { tone: 'unassigned', colorVar: '--warn-solid', text: 'Unnamed', detail: null, dashed: false };
    case 'UNKNOWN':
      return { tone: 'unknown', colorVar: '--accent', text: 'Unknown', detail: null, dashed: false };
    case 'SPOOF':
      return { tone: 'spoof', colorVar: '--danger-solid', text: 'Spoof', detail: null, dashed: false };
    case 'TOO_SMALL':
      return { tone: 'small', colorVar: '--muted', text: 'Move closer', detail: null, dashed: true };
    default:
      return { tone: 'neutral', colorVar: '--muted', text: face.label || stateLabel(face.state), detail: null, dashed: false };
  }
}

function stateLabel(state: LiveFaceState): string {
  return state === 'LIVE' ? 'Live' : 'Checking...';
}

/** Similarity 0..1 as a whole percentage ("87%"), or null. */
export function formatSimilarity(similarity: number | null | undefined): string | null {
  if (typeof similarity !== 'number' || !Number.isFinite(similarity)) return null;
  return `${Math.round(clamp01(similarity) * 100)}%`;
}

/** Short chip text for the side-panel list. */
export function stateChipText(state: LiveFaceState): string {
  switch (state) {
    case 'KNOWN': return 'Known';
    case 'UNASSIGNED': return 'Unnamed';
    case 'UNKNOWN': return 'Unknown';
    case 'SPOOF': return 'Spoof';
    case 'TOO_SMALL': return 'Too small';
    case 'LIVE': return 'Live';
    default: return 'Checking';
  }
}

/** Exponentially smoothed rate (events/sec) given the ms since the previous event. */
export function smoothRate(prev: number | null, dtMs: number, alpha = 0.2): number | null {
  if (!(dtMs > 0)) return prev;
  const inst = 1000 / dtMs;
  return prev == null ? inst : prev + alpha * (inst - prev);
}

/** Relative luminance of a #rgb / #rrggbb color, or null if it cannot be parsed. */
export function hexLuminance(color: string): number | null {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return null;
  let hex = m[1];
  if (hex.length === 3) hex = hex.split('').map((c) => c + c).join('');
  const ch = [0, 2, 4].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

export const PILL_TEXT_LIGHT = '#ffffff';
export const PILL_TEXT_DARK = '#0c0c0e';

/** Picks white or near-black text, whichever contrasts more with the pill fill. */
export function pillTextColor(fill: string): string {
  const l = hexLuminance(fill);
  if (l == null) return PILL_TEXT_LIGHT;
  const onWhite = 1.05 / (l + 0.05);
  const onDark = (l + 0.05) / (0.0039 + 0.05);
  return onWhite >= onDark ? PILL_TEXT_LIGHT : PILL_TEXT_DARK;
}

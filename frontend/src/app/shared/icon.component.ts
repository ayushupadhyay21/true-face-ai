import { Component, input } from '@angular/core';

export type IconName =
  | 'logo'
  | 'scan'
  | 'user-plus'
  | 'camera'
  | 'camera-off'
  | 'check'
  | 'check-circle'
  | 'x'
  | 'alert'
  | 'question'
  | 'users'
  | 'clock'
  | 'shield'
  | 'refresh'
  | 'play'
  | 'stop'
  | 'sun'
  | 'moon'
  | 'move'
  | 'eye'
  | 'hand'
  | 'frame'
  | 'sparkle'
  | 'info';

/** Small inline SVG icon set (stroke icons, currentColor). Purely decorative: aria-hidden. */
@Component({
  selector: 'app-icon',
  host: { style: 'display: contents' },
  template: `
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      @switch (name()) {
        @case ('logo') {
          <svg:path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" />
          <svg:circle cx="12" cy="10.5" r="3" /><svg:path d="M7.5 17.5c1-2 2.6-3 4.5-3s3.5 1 4.5 3" />
        }
        @case ('scan') {
          <svg:path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" />
          <svg:path d="M4 12h16" />
        }
        @case ('user-plus') {
          <svg:circle cx="9" cy="8" r="4" /><svg:path d="M2 21c0-4 3-6 7-6s7 2 7 6" /><svg:path d="M19 8v6M16 11h6" />
        }
        @case ('camera') {
          <svg:path d="M3 8a2 2 0 0 1 2-2h2l2-2h6l2 2h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><svg:circle cx="12" cy="13" r="3.5" />
        }
        @case ('camera-off') {
          <svg:path d="M3 3l18 18" /><svg:path d="M9 4h6l2 2h2a2 2 0 0 1 2 2v9M17 20H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h1" />
          <svg:path d="M9.5 10.5a3.5 3.5 0 0 0 5 5" />
        }
        @case ('check') { <svg:path d="M5 12.5l4.5 4.5L19 7.5" /> }
        @case ('check-circle') { <svg:circle cx="12" cy="12" r="9" /><svg:path d="M8 12.5l3 3 5-6" /> }
        @case ('x') { <svg:path d="M6 6l12 12M18 6L6 18" /> }
        @case ('alert') { <svg:path d="M12 3.5L2.5 20h19z" /><svg:path d="M12 10v4.5M12 17.5v.01" /> }
        @case ('question') {
          <svg:circle cx="12" cy="12" r="9" /><svg:path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17v.01" />
        }
        @case ('users') {
          <svg:circle cx="9" cy="8" r="3.5" /><svg:path d="M2.5 20c0-3.6 2.9-5.5 6.5-5.5s6.5 1.9 6.5 5.5" />
          <svg:path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c2 .7 3.5 2.4 3.5 5.2" />
        }
        @case ('clock') { <svg:circle cx="12" cy="12" r="9" /><svg:path d="M12 7v5l3 2" /> }
        @case ('shield') { <svg:path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><svg:path d="M9 12l2 2 4-4" /> }
        @case ('refresh') { <svg:path d="M20 11a8 8 0 0 0-14.5-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5L20 16M20 20v-4h-4" /> }
        @case ('play') { <svg:path d="M7 5v14l12-7z" /> }
        @case ('stop') { <svg:rect x="6" y="6" width="12" height="12" rx="2" /> }
        @case ('sun') {
          <svg:circle cx="12" cy="12" r="4" />
          <svg:path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        }
        @case ('moon') { <svg:path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" /> }
        @case ('move') { <svg:path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3" /> }
        @case ('eye') { <svg:path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><svg:circle cx="12" cy="12" r="3" /> }
        @case ('hand') {
          <svg:path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V11M11 11V4.5a1.5 1.5 0 0 1 3 0V11M14 11V6a1.5 1.5 0 0 1 3 0v8" />
          <svg:path d="M8 13l-1.6-1.6a1.6 1.6 0 0 0-2.3 2.3L8 18c1.3 1.8 3 3 5.5 3a5.5 5.5 0 0 0 5.5-5.5V14" />
        }
        @case ('frame') { <svg:rect x="3" y="3" width="18" height="18" rx="3" /><svg:circle cx="12" cy="11" r="3.5" /><svg:path d="M7 19c1-2.5 2.8-3.5 5-3.5s4 1 5 3.5" /> }
        @case ('sparkle') { <svg:path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><svg:path d="M19 17l.7 1.8 1.8.7-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z" /> }
        @default { <svg:circle cx="12" cy="12" r="9" /><svg:path d="M12 11v5M12 8v.01" /> }
      }
    </svg>
  `,
})
export class IconComponent {
  readonly name = input.required<IconName>();
}

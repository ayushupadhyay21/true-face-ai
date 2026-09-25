import { Injectable, signal } from '@angular/core';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'tf-theme';

/** Light by default; the header toggle switches to dark and the choice is remembered per browser. */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<Theme>(readStored());

  constructor() {
    apply(this.theme());
  }

  toggle(): void {
    const next: Theme = this.theme() === 'light' ? 'dark' : 'light';
    this.theme.set(next);
    apply(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // storage blocked (private mode etc.): theme still switches for this page view
    }
  }
}

function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'dark') root.dataset['theme'] = 'dark';
  else delete root.dataset['theme'];
}

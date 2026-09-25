import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset['theme'];
  });

  it('defaults to light', () => {
    const svc = TestBed.inject(ThemeService);
    expect(svc.theme()).toBe('light');
    expect(document.documentElement.dataset['theme']).toBeUndefined();
  });

  it('toggles light <-> dark and remembers the choice', () => {
    const svc = TestBed.inject(ThemeService);
    svc.toggle();
    expect(svc.theme()).toBe('dark');
    expect(document.documentElement.dataset['theme']).toBe('dark');
    expect(localStorage.getItem('tf-theme')).toBe('dark');
    svc.toggle();
    expect(svc.theme()).toBe('light');
    expect(document.documentElement.dataset['theme']).toBeUndefined();
    expect(localStorage.getItem('tf-theme')).toBe('light');
  });
});

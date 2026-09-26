import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { HealthService } from './core/health.service';
import { ThemeService } from './core/theme.service';
import { IconComponent } from './shared/icon.component';
import { StatusBarComponent } from './shared/status-bar.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, StatusBarComponent, IconComponent],
  template: `
    <header class="topbar">
      <a class="brand" routerLink="/live" aria-label="True Face AI home">
        <span class="brand-mark"><app-icon name="logo" /></span>
        <span class="brand-copy">
          <span class="brand-text">True Face AI</span>
          <span class="brand-sub">Face Recognition &amp; Liveness</span>
        </span>
      </a>
      <div class="header-right">
        <div class="status-pills" role="status" aria-label="Backend status">
          @if (health.health(); as h) {
            <span class="chip">
              <span class="dot" [class.ok]="h.status === 'ok'" [class.bad]="h.status !== 'ok'"></span>
              Backend <b>{{ h.status === 'ok' ? 'OK' : h.status }}</b>
            </span>
            <span class="chip">
              <span class="dot" [class.ok]="h.database_ok" [class.bad]="!h.database_ok"></span>
              Database <b>{{ h.database_ok ? 'OK' : 'down' }}</b>
            </span>
          } @else if (health.error()) {
            <span class="chip"><span class="dot bad"></span> Backend <b>unreachable</b></span>
          } @else {
            <span class="chip"><span class="dot pending"></span> Backend <b>checking...</b></span>
          }
          <span class="chip">
            @if (health.models(); as m) {
              <span class="dot" [class.ok]="m.calibrated" [class.warn]="!m.calibrated"></span>
              Models <b>{{ m.calibrated ? 'Calibrated' : 'not calibrated' }}</b>
            } @else {
              <span class="dot"></span> Models <b>-</b>
            }
          </span>
        </div>
        <button type="button" class="icon-btn" (click)="health.refresh()" aria-label="Refresh backend status" title="Refresh">
          <app-icon name="refresh" />
        </button>
        <button type="button" class="icon-btn" (click)="theme.toggle()"
                [attr.aria-label]="theme.theme() === 'light' ? 'Switch to dark theme' : 'Switch to light theme'"
                [attr.title]="theme.theme() === 'light' ? 'Dark mode' : 'Light mode'">
          <app-icon [name]="theme.theme() === 'light' ? 'moon' : 'sun'" />
        </button>
        <span class="icon-btn avatar" aria-hidden="true">
          <app-icon name="user-circle" />
        </span>
      </div>
    </header>

    <div class="shell-body">
      <aside class="sidebar">
        <nav class="side-nav" aria-label="Main">
          <a routerLink="/live" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="camera" /> Live View
          </a>
          <a routerLink="/people" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="users" /> People
          </a>
          <a routerLink="/recognize" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="scan" /> Recognize
          </a>
          <a routerLink="/enroll" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="user-plus" /> Enroll
          </a>
          <a routerLink="/settings" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="settings" /> Settings
          </a>
        </nav>
      </aside>
      <main>
        <app-status-bar />
        <router-outlet />
      </main>
    </div>
  `,
})
export class App {
  protected readonly theme = inject(ThemeService);
  protected readonly health = inject(HealthService);
}

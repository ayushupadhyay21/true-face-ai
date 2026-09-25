import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ThemeService } from './core/theme.service';
import { IconComponent } from './shared/icon.component';
import { StatusBarComponent } from './shared/status-bar.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, StatusBarComponent, IconComponent],
  template: `
    <header class="topnav">
      <a class="brand" routerLink="/live" aria-label="True Face AI home">
        <span class="brand-mark"><app-icon name="logo" /></span>
        <span class="brand-text">True Face <span>AI</span></span>
      </a>
      <div class="header-right">
        <nav class="nav-pills" aria-label="Main">
          <a routerLink="/live" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="users" /> Live
          </a>
          <a routerLink="/recognize" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="scan" /> Recognize
          </a>
          <a routerLink="/enroll" routerLinkActive="active" ariaCurrentWhenActive="page">
            <app-icon name="user-plus" /> Enroll
          </a>
        </nav>
        <button type="button" class="theme-toggle" (click)="theme.toggle()"
                [attr.aria-label]="theme.theme() === 'light' ? 'Switch to dark theme' : 'Switch to light theme'"
                [attr.title]="theme.theme() === 'light' ? 'Dark mode' : 'Light mode'">
          <app-icon [name]="theme.theme() === 'light' ? 'moon' : 'sun'" />
        </button>
      </div>
    </header>
    <app-status-bar />
    <main>
      <router-outlet />
    </main>
  `,
})
export class App {
  protected readonly theme = inject(ThemeService);
}

import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { StatusBarComponent } from './shared/status-bar.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, StatusBarComponent],
  template: `
    <header class="topnav">
      <span class="brand">Face Liveness Research</span>
      <nav>
        <a routerLink="/recognize" routerLinkActive="active">Recognize</a>
        <a routerLink="/enroll" routerLinkActive="active">Enroll</a>
      </nav>
    </header>
    <app-status-bar />
    <main>
      <router-outlet />
    </main>
  `,
})
export class App {}

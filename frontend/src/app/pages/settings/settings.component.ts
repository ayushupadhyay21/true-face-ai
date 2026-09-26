import { Component } from '@angular/core';

import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-settings',
  imports: [IconComponent],
  template: `
    <section class="page">
      <header class="page-header">
        <span class="eyebrow"><app-icon name="settings" /> Settings</span>
        <h1>Settings</h1>
        <p class="lead">Nothing configurable here yet.</p>
      </header>
    </section>
  `,
})
export class SettingsComponent {}

import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'live' },
  {
    path: 'recognize',
    title: 'Face Verification',
    loadComponent: () => import('./pages/recognize/recognize.component').then((m) => m.RecognizeComponent),
  },
  {
    path: 'live',
    title: 'Live View',
    loadComponent: () => import('./pages/live/live.component').then((m) => m.LiveComponent),
  },
  {
    path: 'enroll',
    title: 'Enroll',
    loadComponent: () => import('./pages/enroll/enroll.component').then((m) => m.EnrollComponent),
  },
  { path: '**', redirectTo: 'live' },
];

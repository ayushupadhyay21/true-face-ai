import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'recognize' },
  {
    path: 'recognize',
    title: 'Face Verification',
    loadComponent: () => import('./pages/recognize/recognize.component').then((m) => m.RecognizeComponent),
  },
  {
    path: 'enroll',
    title: 'Enroll',
    loadComponent: () => import('./pages/enroll/enroll.component').then((m) => m.EnrollComponent),
  },
  { path: '**', redirectTo: 'recognize' },
];

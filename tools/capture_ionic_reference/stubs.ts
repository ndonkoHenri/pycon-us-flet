// Minimal stand-ins for the Angular, RxJS and Ionic imports of Ionic's
// conference-data.ts (#66). processData uses none of them: they exist only so the
// copied file bundles unchanged. capture.py points each package name here with
// esbuild's --alias.

export function Injectable(_options?: unknown) {
  return (target: unknown) => target;
}

export class HttpClient {}
export class Storage {}
export class ToastController {}
export class Observable {}

export function of(..._values: unknown[]): never {
  throw new Error('rxjs is stubbed: only processData can run');
}

export const map = of;
export const timeout = of;
export const catchError = of;

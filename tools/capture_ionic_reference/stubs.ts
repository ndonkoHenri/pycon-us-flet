// Minimal stand-ins for the Angular, RxJS, Ionic and Capacitor imports of Ionic's
// conference-data.ts (#66) and pycon-api.ts (#662). processData and
// buildRequestAuthHeaders use none of them: they exist only so the copied files bundle
// unchanged. capture.py and capture_signing.py point each package name here with
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

export const Network = {
  getStatus(): never {
    throw new Error('@capacitor/network is stubbed: only buildRequestAuthHeaders can run');
  },
};

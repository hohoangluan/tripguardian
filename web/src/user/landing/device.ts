// Phones get the "use the app" page instead of the landing (docs/UI_SPEC_LANDING.md §5).
// Store links come from the build env (web/.env: VITE_APP_IOS_URL, VITE_APP_ANDROID_URL); empty = not released yet.
export const APP_LINKS = {
  ios: (import.meta.env.VITE_APP_IOS_URL as string | undefined)?.trim() || '',
  android: (import.meta.env.VITE_APP_ANDROID_URL as string | undefined)?.trim() || '',
}

export type Platform = 'ios' | 'android' | 'other'
export function platform(): Platform {
  const ua = navigator.userAgent
  if (/iPhone|iPod|iPad/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios'
  if (/Android/i.test(ua)) return 'android'
  return 'other'
}

// A phone, not a narrow desktop window: a mobile UA, or a touch-only screen too small for the 3D model.
export function isPhone() {
  if (typeof navigator === 'undefined') return false
  if (/iPhone|iPod|Android.+Mobile|Windows Phone|Mobi/i.test(navigator.userAgent)) return true
  const touchOnly = matchMedia('(pointer: coarse)').matches && !matchMedia('(any-pointer: fine)').matches
  return touchOnly && Math.min(screen.width, screen.height) < 600
}

// Notifications on the web (docs/COMPANION.md §Thông báo): the push opt-in after a plan is confirmed, the inbox and
// the per-kind switches. Asking for permission only ever follows a click on "Bật thông báo".
import { json } from './journey'
import { track } from './events'

export type Note = { id: string; kind: string; title: string; body: string; url: string; sent_at: string; opened: boolean }
export type Prefs = { kinds: string[]; enabled_kinds: string[]; quiet_start: string; quiet_end: string; paused: boolean; push_devices: number }

export const KIND_LABEL: Record<string, string> = {
  plan_unfinished: 'Nhắc khi lịch còn dang dở',
  book_ahead: 'Nơi nên đặt trước',
  eve_of_trip: 'Tối trước ngày đi: thời tiết và đồ mang theo',
  day_brief: 'Bản tin sáng mỗi ngày đi',
  checkin_hint: 'Gợi ý bấm Đã đến ở hai điểm đầu',
  golden_hour: 'Giờ hoàng hôn ở nơi trong lịch',
  weather_change: 'Khi dự báo đổi làm ảnh hưởng nơi ngoài trời',
  post_trip: 'Hỏi thăm sau chuyến',
}

const send = <T>(method: string, url: string, body: unknown) => fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(json<T>)

export const loadInbox = () => fetch('/api/harness/notifications').then(json<Note[]>)
export const openNote = (id: string, action?: string) => send('POST', `/api/harness/notifications/${id}/open`, action ? { action } : {}).catch(() => {})
export const loadPrefs = () => fetch('/api/harness/me/notification-prefs').then(json<Prefs>)
export const savePrefs = (patch: Partial<Pick<Prefs, 'enabled_kinds' | 'paused'>>) => send<Prefs>('PATCH', '/api/harness/me/notification-prefs', patch)

export const pushSupported = () => typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

function keyBytes(b64: string) {
  const s = atob((b64 + '='.repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(s, (c) => c.charCodeAt(0))
}

// The browser asks only now, after the user chose "Bật thông báo".
export async function enablePush(): Promise<'granted' | 'denied' | 'default' | 'unsupported' | 'failed'> {
  if (!pushSupported()) return 'unsupported'
  const result = await Notification.requestPermission()
  track('push_permission', { result })
  if (result !== 'granted') return result
  try {
    const reg = await navigator.serviceWorker.register('/sw.js')
    const { key } = await fetch('/api/harness/push/key').then(json<{ key: string }>)
    const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }))
    await send('POST', '/api/harness/push/subscribe', { subscription: sub.toJSON() })
    return 'granted'
  } catch {
    return 'failed'
  }
}

// TripGuardian service worker: web push only (docs/COMPANION.md §Thông báo). No offline cache.
// A push shows the note; a click marks it opened and opens its deep link (?n=<id>).
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

self.addEventListener('push', (e) => {
  let n = {}
  try { n = e.data ? e.data.json() : {} } catch { n = { title: 'TripGuardian', body: e.data ? e.data.text() : '' } }
  e.waitUntil(self.registration.showNotification(n.title || 'TripGuardian', {
    body: n.body || '', icon: '/img/apple-touch-icon.png', badge: '/img/favicon.png', tag: n.id, data: { id: n.id, url: n.url || '/app/today' },
  }))
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const { id, url } = e.notification.data || {}
  e.waitUntil((async () => {
    if (id) await fetch(`/api/harness/notifications/${id}/open`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{"action":"push_click"}' }).catch(() => {})
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const same = wins.find((w) => new URL(w.url).origin === self.location.origin)
    if (same) { await same.focus(); return same.navigate(url) }
    return self.clients.openWindow(url)
  })())
})

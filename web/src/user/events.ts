// Usage events for Admin analytics (docs/ANALYTICS.md §Client). Batched to POST /api/harness/events; the server keeps
// only allowlisted names and props. Never put typed text, names or emails here.

type Name = 'page_view' | 'landing_cta' | 'card_impression' | 'detail_open' | 'evidence_play' | 'compare_open' | 'outbound_click' | 'tab_hidden' | 'today_open' | 'suggestion_open' | 'install_prompt_seen' | 'push_permission'
type Ev = { name: Name; props?: Record<string, string | number | boolean | null>; journey_id?: string }

const URL_ = '/api/harness/events'
const MAX = 50
let queue: Ev[] = []
let journey: string | null = null
let timer: number | undefined
const seen = new Set<string>()

export const setEventJourney = (id: string | null) => { journey = id }

function body(batch: Ev[]) {
  return JSON.stringify({ events: batch })
}

export function flush(beacon = false) {
  if (!queue.length) return
  const batch = queue.splice(0, MAX)
  if (beacon && navigator.sendBeacon) navigator.sendBeacon(URL_, new Blob([body(batch)], { type: 'application/json' }))
  else void fetch(URL_, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body(batch), keepalive: true }).catch(() => {})
  if (queue.length) flush(beacon)
}

export function track(name: Name, props?: Ev['props']) {
  queue.push({ name, props, ...(journey ? { journey_id: journey } : {}) })
  if (queue.length >= 20) flush()
  else if (timer === undefined) timer = window.setTimeout(() => { timer = undefined; flush() }, 10000)
}

// A card counted once per journey: impressions are only a denominator (a card shown and not tapped says nothing).
export function impression(placeId: string, group: string, rank: number) {
  const key = `${journey}:${placeId}`
  if (seen.has(key)) return
  seen.add(key)
  track('card_impression', { place_id: placeId, group, rank })
}

const stageOf = (path: string) => (path.startsWith('/app/explore') ? 'decision' : path.startsWith('/app/plan') ? 'planning' : path.startsWith('/app/understand') ? 'trip' : 'other')

if (typeof window !== 'undefined') {
  // Time spent away from the tab while choosing places: a proxy for having to look things up elsewhere.
  let hiddenAt = 0
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      hiddenAt = Date.now()
      flush(true)
    } else if (hiddenAt) {
      track('tab_hidden', { stage: stageOf(location.pathname), ms: Date.now() - hiddenAt })
      hiddenAt = 0
    }
  })
  addEventListener('pagehide', () => flush(true))
}

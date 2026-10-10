// Pure helpers of the Lịch trình screen (no React, no network): how a plan is read, ordered and grouped for display.
import type { CrowdTip, DayConditions, ItineraryDay, ItineraryItem, Variant, Warning } from './types'

type Fit = { stars: number; level: string } | null | undefined

// The vehicle of a leg (backend Item.mode, docs/P4_PLANNING.md §Phương tiện): bike for a motorbike, car for a car, a walker on foot.
export const LEG_ICON: Record<string, 'bike' | 'car' | 'walk'> = { motorbike: 'bike', car: 'car', walk: 'walk' }
export const LEG_WORD: Record<string, string> = { motorbike: 'Xe máy', car: 'Ô tô', walk: 'Đi bộ' }

// How a leg is travelled: the vehicle of its longest part that is not a walk (parking then a short walk shows the
// vehicle); a leg that is only walking shows a walker. null when the plan carries no mode.
export function legMode(parts: { mode?: string; min: number }[]): string | null {
  let best: { mode: string; min: number } | null = null
  let walk: string | null = null
  for (const p of parts) {
    if (!p.mode) continue
    if (p.mode === 'walk') walk = 'walk'
    else if (!best || p.min > best.min) best = { mode: p.mode, min: p.min }
  }
  return best?.mode ?? walk
}

export interface MealOption { place_id: string; name: string; km: number }

// Suggestions are ordered by the trip's own "Hợp với bạn" stars (Card.fit, read, never recomputed), then by the shorter
// way from the stop they sit next to (equal ways: the higher stars). Stars count in half-star bands so a 4.1 and a 4.0 do not outrank a place 2 km
// closer; a place with no fit (the trip names no taste, or the place is not a Decision card) goes after those that have one.
export function rankOptions<T extends { place_id: string; km: number }>(options: T[], fitOf: (id: string) => Fit): T[] {
  const stars = (id: string) => fitOf(id)?.stars ?? -1
  const band = (id: string) => (fitOf(id) ? Math.floor(stars(id) * 2) : -1)
  return [...options].sort((a, b) => band(b.place_id) - band(a.place_id) || a.km - b.km || stars(b.place_id) - stars(a.place_id) || a.place_id.localeCompare(b.place_id))
}

// Up to n places to picture a variant by: the first stop of each day first (they differ most between plans), then the
// rest in order; places with a photo before those without, and a day-opening stop that every variant shares last, so
// two plans do not open on the same picture when they have others to show.
const firstStops = (v: Pick<Variant, 'itinerary'>) => v.itinerary.map((d) => d.items.find((it: ItineraryItem) => it.kind === 'visit' && it.place_id)?.place_id).filter((x): x is string => !!x)
export function variantPlaces(v: Pick<Variant, 'itinerary'>, hasPhoto: (id: string) => boolean, n = 3, all: Pick<Variant, 'itinerary'>[] = [v]): string[] {
  const shared = new Set(firstStops(v).filter((id) => all.every((o) => firstStops(o).includes(id))))
  const stops = v.itinerary.flatMap((d) => d.items.filter((it: ItineraryItem) => it.kind === 'visit' && it.place_id).map((it) => it.place_id!))
  const order = [...new Set([...firstStops(v), ...stops])]
  const rank = (id: string) => (hasPhoto(id) ? 0 : 2) + (shared.has(id) && all.length > 1 ? 1 : 0)
  return order.map((id, i) => ({ id, i })).sort((a, b) => rank(a.id) - rank(b.id) || a.i - b.i).map((x) => x.id).slice(0, n)
}

// What each objective means in a sentence (the label itself comes from the backend, src/planning/objectives.py LABEL).
export const OBJECTIVE_BLURB: Record<string, string> = {
  least_travel: 'Ít đi lại nhất: các nơi gần nhau xếp cùng ngày.',
  low_cost: 'Chi phí thấp nhất trong các cách xếp.',
  weather_robust: 'Ít nơi ngoài trời vào ngày mưa.',
  diverse: 'Mỗi ngày một kiểu trải nghiệm khác nhau.',
  preference_fit: 'Sát gu bạn đã nói nhất.',
}

// Trip-wide warnings (View.warnings + the chosen variant's), by what the reader has to do about them.
// need: act or check before going; rough: the plan says what it assumed or estimated (nothing to do).
const NEED = new Set(['hours_unknown', 'hours_vary', 'meal_missed', 'early_start', 'pin_dropped', 'severe_weather', 'heavy_weather', 'advisory', 'crowd_day', 'holiday_closure', 'lodging_unavailable', 'flag'])
export interface Note { code: string; lead: string | null; text: string }
// "Ngày 2: …" and "Tên nơi: …" start with a lead the reader scans for; the rest is the sentence.
export function toNote(w: Warning): Note {
  const m = /^([^:.]{2,48}): (.+)$/.exec(w.text)
  return m ? { code: w.code, lead: m[1], text: m[2] } : { code: w.code, lead: null, text: w.text }
}
// Notes of one code that name a place each (hours_unknown, hours_vary) become a single line once there are two or more.
const MERGE: Record<string, { lead: (n: number) => string; tail: string }> = {
  hours_unknown: { lead: (n) => `Chưa có giờ mở cửa (${n} nơi)`, tail: 'Bạn hỏi lại trước khi đi nhé.' },
  hours_vary: { lead: (n) => `Giờ mở cửa khác nhau theo thứ (${n} nơi)`, tail: 'Chưa biết ngày đi nên mình dùng khung giờ chung các ngày mở.' },
}
export function groupNotes(warnings: Warning[]) {
  const seen = new Set<string>()
  const notes = warnings.filter((w) => w.code !== 'walk_only' && !seen.has(w.text) && !!seen.add(w.text)).map(toNote)
  const merged: Note[] = []
  for (const n of notes) {
    const m = MERGE[n.code]
    if (!m || !n.lead) { merged.push(n); continue }
    const same = notes.filter((x) => x.code === n.code && x.lead)
    if (same.length < 2) { merged.push(n); continue }
    if (same[0] === n) merged.push({ code: n.code, lead: m.lead(same.length), text: `${same.map((x) => x.lead).join(', ')}. ${m.tail}` })
  }
  return { need: merged.filter((n) => NEED.has(n.code)), rough: merged.filter((n) => !NEED.has(n.code)) }
}
export const walkOnly = (warnings: Warning[]) => warnings.find((w) => w.code === 'walk_only')

export const RENTAL_NOTE = {
  pickup: 'Ngày đầu mở sau giờ bạn đến, đã cộng thời gian nhận xe máy thuê.',
  return: 'Ngày cuối đóng sớm hơn giờ bạn rời để kịp trả xe máy thuê.',
  both: 'Ngày này đã chừa thời gian nhận xe máy thuê khi đến và trả xe trước khi rời.',
}

// A trip that arrives by coach or plane and rides a motorbike rents it in the city (docs/P4_PLANNING.md §Thuê xe máy):
// day one opens after the pickup, the last day closes before the return.
export const rentsBike = (ctx: { arrival_mode?: string | null; mobility?: string | null } | undefined) => !!ctx && (ctx.arrival_mode === 'bus' || ctx.arrival_mode === 'plane') && ctx.mobility === 'motorbike'
// Which rental step touches a day: pickup (day one opens after it), return (the last day closes before it), both (a
// one-day trip), or none. Only when the traveller gave the time the step is measured from.
export function rentalStep(ctx: { arrival_mode?: string | null; mobility?: string | null; checkin_at?: string | null; checkout_at?: string | null } | undefined, dayIndex: number, dayCount: number): 'pickup' | 'return' | 'both' | null {
  if (!rentsBike(ctx)) return null
  const pickup = dayIndex === 0 && !!ctx!.checkin_at
  const back = dayIndex === dayCount - 1 && !!ctx!.checkout_at
  return pickup && back ? 'both' : pickup ? 'pickup' : back ? 'return' : null
}

// A stop dropped on another stop of its day lands before or after it. null when nothing would change (the drop is on
// itself, or the stop already sits there) or an id is not of this day: the caller then sends nothing.
export function placeAt(order: string[], id: string, target: string, side: 'before' | 'after'): string[] | null {
  if (id === target || !order.includes(id) || !order.includes(target)) return null
  const rest = order.filter((x) => x !== id)
  rest.splice(rest.indexOf(target) + (side === 'after' ? 1 : 0), 0, id)
  return rest.every((x, i) => x === order[i]) ? null : rest
}

// Everything the reader should look at before going, in one list: trip-wide notes, each day's conditions and the notes
// the plan put on a stop. warn: check or act; info: only how rough the plan is. A day with no notice adds nothing; the
// screen says "no notice" once and never "all clear".
export type AlertIcon = 'rain' | 'users' | 'calendar' | 'clock' | 'warn' | 'utensils' | 'info'
export interface Alert { key: string; level: 'warn' | 'info'; icon: AlertIcon; day: number | null; lead: string | null; text: string }
export const NOTE_ICON: Record<string, AlertIcon> = { severe_weather: 'rain', heavy_weather: 'rain', advisory: 'warn', crowd_day: 'users', holiday_closure: 'calendar', hours_unknown: 'clock', hours_vary: 'clock', early_start: 'clock', meal_missed: 'utensils', pin_dropped: 'clock' }
export const ADVISORY: Record<string, string> = { storm: 'bão / dông', flood: 'ngập lụt', landslide: 'sạt lở', fire: 'cháy', road_closed: 'đường bị chặn', other: 'khác' }

function dayAlerts(c: DayConditions, tips: CrowdTip[]): Omit<Alert, 'key'>[] {
  const day = c.day
  const out: Omit<Alert, 'key'>[] = []
  if (c.weather !== 'none') {
    const what = [c.storm ? 'dông' : '', c.rain_mm ? `mưa ~${Math.round(c.rain_mm)} mm` : '', c.gust_kmh ? `gió giật ~${Math.round(c.gust_kmh)} km/h` : ''].filter(Boolean).join(', ')
    out.push({ level: 'warn', icon: 'rain', day, lead: null, text: `${c.weather === 'severe' ? 'Thời tiết rất xấu' : 'Mưa lớn hoặc dông'}${what ? ` (${what})` : ''}` })
  }
  for (const a of c.advisories) out.push({ level: 'warn', icon: 'warn', day, lead: null, text: `Thông báo ${ADVISORY[a.kind] ?? a.kind}: ${a.note || 'xem nguồn'} (${a.source})` })
  if (c.crowd !== 'normal') out.push({ level: 'warn', icon: 'users', day, lead: null, text: `${c.crowd === 'peak' ? 'Rất đông' : 'Đông hơn thường'}: ${c.crowd_reasons.join(', ')}` })
  if (c.day_type === 'holiday') out.push({ level: 'warn', icon: 'calendar', day, lead: null, text: 'Ngày lễ' })
  if (c.closure_risk) out.push({ level: 'warn', icon: 'warn', day, lead: null, text: `Dịp ${c.closure_risk}: nhiều quán đóng cửa hoặc đổi giờ, gọi xác nhận trước` })
  if (c.crowd !== 'normal') for (const t of tips.slice(0, 2)) out.push({ level: 'info', icon: 'clock', day, lead: null, text: t.text })
  return out
}

export function alertsOf({ warnings, days, conditions, tips }: { warnings: Warning[]; days: ItineraryDay[]; conditions: DayConditions[]; tips: CrowdTip[] }): Alert[] {
  const { need, rough } = groupNotes(warnings)
  const list: Omit<Alert, 'key'>[] = [
    ...conditions.flatMap((c) => dayAlerts(c, tips)),
    ...days.flatMap((d) => d.items.filter((it) => it.kind === 'visit' && it.note && it.note.includes(' ')).map((it): Omit<Alert, 'key'> => ({ level: 'warn', icon: 'warn', day: d.day, lead: it.name ?? null, text: it.note! }))),
    ...need.map((n): Omit<Alert, 'key'> => ({ level: 'warn', icon: NOTE_ICON[n.code] ?? 'warn', day: null, lead: n.lead, text: n.text })),
    ...rough.map((n): Omit<Alert, 'key'> => ({ level: 'info', icon: 'info', day: null, lead: n.lead, text: n.text })),
  ]
  const seen = new Set<string>()
  const alerts = list.filter((a) => { const k = `${a.day}|${a.lead}|${a.text}`; return !seen.has(k) && !!seen.add(k) }).map((a, i) => ({ ...a, key: `${i}-${a.day}-${a.text.slice(0, 24)}` }))
  const byDay = (a: Alert, b: Alert) => (a.day ?? Infinity) - (b.day ?? Infinity)  // days in order, trip-wide notes last
  return [...alerts.filter((a) => a.level === 'warn').sort(byDay), ...alerts.filter((a) => a.level === 'info').sort(byDay)]
}

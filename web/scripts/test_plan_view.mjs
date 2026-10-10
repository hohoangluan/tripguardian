import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
// Compile web/src/user/planning/view.ts with tsc into this path before running this test.
const source = readFileSync(process.env.PLAN_VIEW_JS ?? '/tmp/tg-plan-view/view.js', 'utf8')
const v = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

test('meal suggestions: Card.fit stars first (half-star bands), then the shorter way, no fit last', () => {
  const fit = { a: { stars: 4.6, level: 'x' }, b: { stars: 4.1, level: 'x' }, c: { stars: 4.4, level: 'x' }, e: { stars: 2, level: 'x' } }
  const opts = [{ place_id: 'e', km: 0.1 }, { place_id: 'd', km: 0.2 }, { place_id: 'b', km: 1.8 }, { place_id: 'c', km: 0.4 }, { place_id: 'a', km: 1.9 }]
  const ranked = v.rankOptions(opts, (id) => fit[id])
  // a 4.6 beats everything; c (4.4) and b (4.1) are the same 4.0-4.5 band... 4.4 -> band 8, 4.1 -> band 8: the nearer c goes first
  assert.deepEqual(ranked.map((o) => o.place_id), ['a', 'c', 'b', 'e', 'd'])
  assert.deepEqual(opts.map((o) => o.place_id), ['e', 'd', 'b', 'c', 'a']) // input untouched
})
test('meal suggestions with no fit anywhere are ordered by distance', () => {
  const ranked = v.rankOptions([{ place_id: 'x', km: 1.5 }, { place_id: 'y', km: 0.3 }], () => null)
  assert.deepEqual(ranked.map((o) => o.place_id), ['y', 'x'])
})
test('leg mode: longest non-walk part, a walk only when nothing else', () => {
  assert.equal(v.legMode([{ mode: 'car', min: 12 }, { mode: 'walk', min: 4 }]), 'car')
  assert.equal(v.legMode([{ mode: 'walk', min: 4 }]), 'walk')
  assert.equal(v.legMode([{ mode: 'motorbike', min: 5 }, { mode: 'car', min: 9 }]), 'car')
  assert.equal(v.legMode([{ min: 5 }]), null)
})
test('trip notes: walk_only is not a note, duplicates drop, hours notes merge, need vs rough', () => {
  const w = (code, text) => ({ code, text })
  const { need, rough } = v.groupNotes([
    w('walk_only', 'Bạn không thuê xe nên lịch chỉ đi bộ.'),
    w('hours_unknown', 'Quán A: chưa có giờ mở cửa, bạn hỏi lại trước khi đi nhé.'),
    w('hours_unknown', 'Quán B: chưa có giờ mở cửa, bạn hỏi lại trước khi đi nhé.'),
    w('heavy_weather', 'Ngày 2: dự báo mưa lớn.'),
    w('heavy_weather', 'Ngày 2: dự báo mưa lớn.'),
    w('travel_rough', 'Giờ di chuyển được ước tính.'),
  ])
  assert.equal(v.walkOnly([w('walk_only', 'x')]).code, 'walk_only')
  assert.deepEqual(need.map((n) => n.code), ['hours_unknown', 'heavy_weather'])
  assert.match(need[0].lead, /2 nơi/)
  assert.equal(need[0].text.startsWith('Quán A, Quán B. Bạn hỏi lại'), true)
  assert.deepEqual(need[1], { code: 'heavy_weather', lead: 'Ngày 2', text: 'dự báo mưa lớn.' })
  assert.deepEqual(rough.map((n) => n.code), ['travel_rough'])
})
test('rental step: only for a coach / plane arrival on a motorbike, from the times given', () => {
  const ctx = { arrival_mode: 'plane', mobility: 'motorbike', checkin_at: '10:00', checkout_at: '16:00' }
  assert.equal(v.rentalStep(ctx, 0, 3), 'pickup')
  assert.equal(v.rentalStep(ctx, 1, 3), null)
  assert.equal(v.rentalStep(ctx, 2, 3), 'return')
  assert.equal(v.rentalStep(ctx, 0, 1), 'both')
  assert.equal(v.rentalStep({ ...ctx, checkout_at: null }, 2, 3), null)
  assert.equal(v.rentalStep({ ...ctx, arrival_mode: 'self' }, 0, 3), null)
  assert.equal(v.rentalStep({ ...ctx, mobility: 'car' }, 0, 3), null)
})
test('variant photos: first stop of each day, places with a photo first', () => {
  const day = (...ids) => ({ items: ids.map((id) => ({ kind: 'visit', place_id: id })) })
  const plan = { itinerary: [day('a1', 'a2'), day('b1', 'b2'), day('c1')] }
  assert.deepEqual(v.variantPlaces(plan, () => true), ['a1', 'b1', 'c1'])
  assert.deepEqual(v.variantPlaces(plan, (id) => id !== 'b1'), ['a1', 'c1', 'a2'])
})
test('meal suggestions: the same way and the same band, the higher stars first', () => {
  const fit = { a: { stars: 0.68, level: 'x' }, b: { stars: 0.84, level: 'x' } }
  const ranked = v.rankOptions([{ place_id: 'a', km: 0.2 }, { place_id: 'b', km: 0.2 }], (id) => fit[id])
  assert.deepEqual(ranked.map((o) => o.place_id), ['b', 'a'])
})
test('variant photos: a day-opening stop every variant shares goes after the stops that tell the plans apart', () => {
  const day = (...ids) => ({ items: ids.map((id) => ({ kind: 'visit', place_id: id })) })
  const a = { itinerary: [day('s', 'x'), day('a1')] }
  const b = { itinerary: [day('s', 'y'), day('b1')] }
  assert.deepEqual(v.variantPlaces(a, () => true, 3, [a, b]), ['a1', 'x', 's'])
  assert.deepEqual(v.variantPlaces(b, () => true, 3, [a, b]), ['b1', 'y', 's'])
})
test('drop order: a stop lands before or after the one it was dropped on; a drop that changes nothing is null', () => {
  assert.deepEqual(v.placeAt(['a', 'b', 'c'], 'a', 'c', 'after'), ['b', 'c', 'a'])
  assert.deepEqual(v.placeAt(['a', 'b', 'c'], 'c', 'a', 'before'), ['c', 'a', 'b'])
  assert.deepEqual(v.placeAt(['a', 'b', 'c'], 'a', 'c', 'before'), ['b', 'a', 'c'])
  assert.equal(v.placeAt(['a', 'b', 'c'], 'b', 'a', 'after'), null) // already there
  assert.equal(v.placeAt(['a', 'b', 'c'], 'b', 'c', 'before'), null)
  assert.equal(v.placeAt(['a', 'b'], 'a', 'a', 'before'), null) // onto itself
  assert.equal(v.placeAt(['a', 'b'], 'x', 'a', 'before'), null) // not of this day
  assert.equal(v.placeAt(['a', 'b'], 'a', 'x', 'after'), null)
})
test('alerts: what the reader must check, worst first, each with the day it concerns', () => {
  const cond = (day, over = {}) => ({ day, date: null, weather: 'none', storm: false, rain_mm: null, gust_kmh: null, day_type: 'weekday', crowd: 'normal', crowd_reasons: [], closure_risk: null, advisories: [], ...over })
  const days = [
    { day: 1, items: [{ kind: 'visit', place_id: 'p1', name: 'Hồ Xuân Hương', note: 'Đóng cửa thứ hai' }, { kind: 'visit', place_id: 'p2', name: 'Chợ', note: 'code_only' }] },
    { day: 2, items: [] },
    { day: 3, items: [] },
  ]
  const alerts = v.alertsOf({
    warnings: [{ code: 'travel_rough', text: 'Giờ di chuyển được ước tính.' }, { code: 'hours_unknown', text: 'Quán A: chưa có giờ mở cửa, bạn hỏi lại trước khi đi nhé.' }],
    days,
    conditions: [cond(1, { weather: 'severe', storm: true, rain_mm: 30 }), cond(2, { advisories: [{ kind: 'road_closed', severity: 'high', note: 'Đèo Prenn', source: 'UBND' }] }), cond(3, { day_type: 'weekend' })],
    tips: [],
  })
  assert.deepEqual(alerts.map((a) => a.level), ['warn', 'warn', 'warn', 'warn', 'info'])
  assert.deepEqual(alerts.map((a) => a.day), [1, 1, 2, null, null])
  assert.match(alerts[0].text, /Thời tiết rất xấu/)
  assert.deepEqual([alerts[1].lead, alerts[1].text], ['Hồ Xuân Hương', 'Đóng cửa thứ hai'])
  assert.match(alerts[2].text, /đường bị chặn.*Đèo Prenn/)
  assert.equal(alerts.some((a) => /code_only/.test(a.text)), false) // a bare code is not a sentence
  assert.equal(alerts.some((a) => a.day === 3), false) // a plain weekend is no alert
  assert.deepEqual(v.alertsOf({ warnings: [], days, conditions: [], tips: [] }).map((a) => a.text), ['Đóng cửa thứ hai'])
})

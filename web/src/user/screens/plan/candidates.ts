import { info } from '../../lib'
import type { ItineraryDay, Variant, View } from '../../planning/types'
import { visits } from './shared'

// Who can come into a day: the server only accepts a place that is in the selection (a dropped one comes back with a move,
// swap) or in the checked backup pool (add_from_backup, swap). Nothing outside those two is offered.
export interface Candidate {
  id: string
  name: string
  from: 'backup' | 'selection'
  why: string | null // why it was set aside, or why it is a stand-in
  forThis: boolean // the stand-in the planner picked for the place being replaced
}

export function candidatesOf(view: View, variant: Variant | null, days: ItineraryDay[], replacing: string | null): Candidate[] {
  const inPlan = new Set(days.flatMap((d) => visits(d).map((it) => it.place_id!)))
  const out = new Map<string, Candidate>()
  const add = (c: Candidate) => {
    if (inPlan.has(c.id) || out.has(c.id)) return
    out.set(c.id, { ...c, name: info(c.id)?.name ?? c.name })
  }
  for (const x of variant?.dropped_by_plan ?? []) if ((view.state.plan_dropped ?? []).includes(x.place_id)) add({ id: x.place_id, name: x.name, from: 'selection', why: x.text, forThis: false })
  for (const x of view.state.dropped) add({ id: x.place_id, name: x.place_id, from: 'selection', why: 'Bạn đã tạm bỏ nơi này', forThis: false })
  const backups = view.backups ?? variant?.backups
  for (const b of backups?.places ?? []) for (const a of b.alternatives) add({ id: a.id, name: a.name, from: 'backup', why: a.reason ?? `Dự phòng cho ${b.name}`, forThis: !!replacing && b.place_id === replacing && a.for_this })
  for (const r of view.recommendations ?? variant?.recommendations ?? []) for (const a of r.alternatives) add({ id: a.id, name: a.name, from: 'backup', why: r.text, forThis: false })
  return [...out.values()].sort((a, b) => Number(b.forThis) - Number(a.forThis) || (info(b.id)?.rating ?? 0) - (info(a.id)?.rating ?? 0))
}

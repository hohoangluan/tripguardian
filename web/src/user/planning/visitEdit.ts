import type { Action } from './types'

export function visitAction(place: string, start: string, duration: string): Action | null {
  if (start && !/^([01]\d|2[0-3]):[0-5]\d$/.test(start)) return null
  if (duration && (!/^\d+$/.test(duration) || Number(duration) < 1 || Number(duration) > 1440)) return null
  return { type: 'set_visit', place, start: start || null, duration_min: duration ? Number(duration) : null }
}

export function automaticVisitAction(place: string, field: 'start' | 'duration_min'): Action {
  return { type: 'set_visit', place, [field]: null }
}

export function moveVisitAction(place: string, displayedDay: number): Action {
  return { type: 'move_place', place, day: displayedDay - 1 }
}

export function reorderVisitAction(displayedDay: number, order: string[]): Action {
  return { type: 'reorder', day: displayedDay - 1, order }
}

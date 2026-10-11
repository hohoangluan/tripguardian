import { useLayoutEffect, useRef, useState } from 'react'
import type { Card, Change } from '../pd/types'

export type Staged = { card: Card; phase: 'stay' | 'enter' | 'leave'; i: number }
const LEAVE_MS = 180
const REPLACE_MS = 240
const SWAP_MS = 110 // the cross-fade is at its faintest here: swap the cards then
const STAGGER_MAX = 8 // a whole new page fades up in about 0.3 s, not one card at a time
export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches
const still = (cards: Card[]): Staged[] => cards.map((card) => ({ card, phase: 'stay', i: 0 }))

// Cards that stay keep their slot, removed ones fade out where they were, new ones fade up into the freed slots.
// `group` changes when the user switches tabs: the new tab's cards just appear, nothing leaves.
export function useStagedList(group: string, cards: Card[], change: Change | undefined) {
  const prev = useRef({ group, cards })
  const [items, setItems] = useState<Staged[]>(() => still(cards))
  const [replacing, setReplacing] = useState(false)
  useLayoutEffect(() => {
    const before = prev.current
    prev.current = { group, cards }
    if (before.group !== group) { setReplacing(false); setItems(still(cards)); return }
    if (before.cards === cards) return
    const now = new Set(cards.map((c) => c.id))
    const was = new Set(before.cards.map((c) => c.id))
    if (change?.replaced_all && !reducedMotion()) {
      setReplacing(true)
      const swap = setTimeout(() => setItems(still(cards)), SWAP_MS)
      const done = setTimeout(() => setReplacing(false), REPLACE_MS)
      return () => { clearTimeout(swap); clearTimeout(done); setReplacing(false); setItems(still(cards)) }
    }
    let n = 0
    const next: Staged[] = cards.map((card) => ({ card, phase: was.has(card.id) ? 'stay' : 'enter', i: was.has(card.id) ? 0 : Math.min(n++, STAGGER_MAX) }))
    const leaving = before.cards.filter((c) => !now.has(c.id))
    if (!leaving.length) { setItems(next); return }
    const merged = [...next]
    before.cards.forEach((c, k) => { if (!now.has(c.id)) merged.splice(Math.min(k, merged.length), 0, { card: c, phase: 'leave', i: 0 }) })
    setItems(merged)
    const t = setTimeout(() => setItems(next), reducedMotion() ? 150 : LEAVE_MS)
    return () => { clearTimeout(t); setItems(next) }
  }, [group, cards, change])
  return { items, replacing }
}

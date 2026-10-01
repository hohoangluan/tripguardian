import type { Place } from '../data/types'

export const fold = (s: string) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/\b(da lat|dalat|tp|thanh pho)\b/g, ' ')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

const STOP = new Set(['quan', 'tiem', 'cafe', 'ca', 'phe', 'coffee', 'nha', 'hang', 'the', 'va', 'cua'])

function tokens(s: string) {
  return fold(s)
    .split(' ')
    .filter((t) => t.length > 1)
}

// Token overlap on distinctive words; never returns a "match" on generic words alone.
export function score(q: string, p: Place) {
  const qt = tokens(q)
  const nt = new Set(tokens(p.name))
  if (!qt.length) return 0
  const fq = fold(q)
  const fn = fold(p.name)
  if (fn === fq) return 1
  const hits = qt.filter((t) => nt.has(t))
  const strong = hits.filter((t) => !STOP.has(t))
  if (!strong.length) return 0
  let s = hits.length / Math.max(qt.length, nt.size)
  if (fn.includes(fq) || fq.includes(fn)) s = Math.max(s, 0.8)
  return s
}

export type MatchResult =
  | { state: 'matched'; place: Place }
  | { state: 'choose'; candidates: Place[] }
  | { state: 'missing' }

// "Túi Mơ To" and "Tiệm Túi Mơ To" resolve to one place; a tie asks the user.
export function resolve(q: string, places: Place[]): MatchResult {
  const ranked = places
    .map((p) => ({ p, s: score(q, p) }))
    .filter((x) => x.s > 0.34)
    .sort((a, b) => b.s - a.s)
  if (!ranked.length) return { state: 'missing' }
  const [first, second] = ranked
  if (first.s >= 0.8 && (!second || first.s - second.s >= 0.25)) return { state: 'matched', place: first.p }
  return { state: 'choose', candidates: ranked.slice(0, 3).map((x) => x.p) }
}

export function search(q: string, places: Place[], limit = 6) {
  if (fold(q).length < 2) return []
  return places
    .map((p) => ({ p, s: score(q, p) + (fold(p.name).startsWith(fold(q)) ? 0.3 : 0) + (p.kind === 'experience' ? 0.05 : 0) }))
    .filter((x) => x.s > 0.2)
    .sort((a, b) => b.s - a.s)
    .slice(0, limit)
    .map((x) => x.p)
}

export const area = (p: Place) => {
  const parts = (p.address ?? '').split(',').map((s) => s.trim())
  return parts.find((s) => /Phường|Xã|Lâm Viên|Xuân|Lang Biang|Cam Ly|Đà Lạt/.test(s)) ?? parts[1] ?? ''
}

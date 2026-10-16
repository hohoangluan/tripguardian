import type { Card } from '../pd/types'

// What a place says about itself, read the same way by every view of it (grid card, rotary disc): up to three
// reasons, the main tradeoff, and up to two alerts. The views differ only in how they draw these lines.
export function cardLines(c: Card): { why: Card['why']; trade: string | undefined; alerts: string[] } {
  const notes = [...c.failed.map((t) => `Không hợp điều kiện của bạn: ${t}`), ...c.unverified, ...c.warnings, ...(c.depends_on_unknown ? [c.depends_on_unknown] : [])]
  const trade = c.tradeoffs[0]?.text ?? notes.shift()
  return { why: c.why.slice(0, 3), trade, alerts: [...c.tradeoffs.slice(1).map((t) => t.text), ...notes].slice(0, 2) }
}

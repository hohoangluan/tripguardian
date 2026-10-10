// One-time hints and tours: remember per browser that the user already saw one.
const PREFIX = 'tg.seen.'

export function hasSeen(key: string): boolean {
  try { return localStorage.getItem(PREFIX + key) === '1' } catch { return false }
}

export function markSeen(key: string): void {
  try { localStorage.setItem(PREFIX + key, '1') } catch { /* private mode: hint may show again */ }
}

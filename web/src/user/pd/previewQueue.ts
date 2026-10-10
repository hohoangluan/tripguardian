interface Request<T> {
  key: string
  run: () => Promise<T>
  ready: (value: T) => void
  error: (error: unknown) => void
  generation: number
}

// Keep the physical request running on cancel; a new stage still waits for it to finish.
export class PreviewQueue<T> {
  private generation = 0
  private active: Request<T> | null = null
  private latest: Request<T> | null = null
  private pending: Request<T> | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private debounced = false
  private completed: { key: string; value: T } | null = null

  constructor(private delay: number) {}

  request(key: string, run: () => Promise<T>, ready: (value: T) => void, error: (error: unknown) => void) {
    const next = { key, run, ready, error, generation: this.generation }
    this.latest = next
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
    this.pending = null
    this.debounced = false
    if (this.completed?.key === key) {
      ready(this.completed.value)
      return
    }
    if (this.active?.key === key && this.active.generation === this.generation) return
    this.pending = next
    this.timer = setTimeout(() => {
      this.timer = null
      this.debounced = true
      this.start()
    }, this.delay)
  }

  cancel() {
    this.generation++
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
    this.latest = this.pending = null
    this.completed = null
    this.debounced = false
  }

  private start() {
    if (this.active || !this.pending || !this.debounced) return
    const request = this.pending
    this.pending = null
    this.active = request
    const current = () => request.generation === this.generation && this.latest?.key === request.key
    void Promise.resolve().then(request.run).then(
      (value) => {
        if (current()) {
          this.completed = { key: request.key, value }
          this.latest!.ready(value)
        }
      },
      (error) => { if (current()) this.latest!.error(error) },
    ).finally(() => {
      this.active = null
      this.start()
    })
  }
}

const canonical = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)]))
  return value
}

export function previewKey(journey: string, selected: string[], locked: string[], constraints: unknown): string {
  return JSON.stringify(canonical({ journey, selected: [...selected].sort(), locked: [...locked].sort(), constraints }))
}

import type { Suggestions, View } from './types'

// Reads begun before an edit and replies from another Planning session cannot replace the screen.
export class PlanningGate {
  private id: string | null = null
  private generation = 0
  private epoch = 0
  private revision = -1
  reset(id: string | null) { this.id = id; this.generation++; this.epoch++; this.revision = -1 }
  invalidate() { this.epoch++ }
  ticket() { return { id: this.id, generation: this.generation, epoch: this.epoch } }
  accept(ticket: ReturnType<PlanningGate['ticket']>, revision: number, mutation = false) {
    if (ticket.id !== this.id || ticket.generation !== this.generation || (!mutation && ticket.epoch !== this.epoch)
      || !Number.isInteger(revision) || revision < this.revision) return false
    this.revision = revision
    return true
  }
}

export function mergeSuggestions(view: View, result: Suggestions): View {
  if (view.suggestions?.token !== result.token || view.suggestions.session_id !== result.session_id) return view
  return { ...view, suggestions: result, recommendations: result.items }
}

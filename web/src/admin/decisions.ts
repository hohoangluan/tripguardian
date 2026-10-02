import { useSyncExternalStore } from 'react'
import { featureDecisions, sendDecision } from './api'

// Reviewer decisions on served values. The review API (data/review/decisions.jsonl) is the record; this browser
// keeps a copy so the screen works when the API is not running, and says so (useBackend).
export type Verdict = 'accept' | 'disable' | 'report' | 'refresh'
export type ReportKind = 'value' | 'link' | 'type' | 'duplicate' | 'category'

export interface Decision {
  id: string
  verdict: Verdict
  report?: ReportKind
  at: string
}

export const REPORT_LABEL: Record<ReportKind, string> = {
  value: 'Giá trị sai',
  link: 'Liên kết sai',
  type: 'Sai loại POI / ZONE',
  duplicate: 'Trùng địa điểm',
  category: 'Sai category',
}

export const VERDICT_LABEL: Record<Verdict, string> = { accept: 'Đã chấp nhận', disable: 'Đã vô hiệu', report: 'Đã báo lỗi', refresh: 'Đã yêu cầu làm mới' }

export type Backend = 'checking' | 'online' | 'offline'

const KEY = 'tg.admin.decisions.v1'
let state: Record<string, Decision> = (() => {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}')
  } catch {
    return {}
  }
})()
let backend: Backend = 'checking'
const subs = new Set<() => void>()
const emit = () => subs.forEach((f) => f())

function keep() {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* kept in memory only */
  }
}

function setBackend(b: Backend) {
  if (b === backend) return
  backend = b
  emit()
}

// The server's latest record per item wins; items it never saw stay as they are in this browser.
export function syncDecisions() {
  featureDecisions().then(
    (server) => {
      state = { ...state }
      for (const [id, rec] of Object.entries(server)) {
        if (rec.decision === 'undo') delete state[id]
        else state[id] = { id, verdict: rec.decision as Verdict, report: rec.decision === 'report' ? (rec.note as ReportKind) : undefined, at: rec.at }
      }
      keep()
      setBackend('online')
      emit()
    },
    () => setBackend('offline'),
  )
}

function push(id: string, decision: string, note = '') {
  sendDecision(id, decision, note).then(
    () => setBackend('online'),
    () => setBackend('offline'),
  )
}

export function decide(ids: string[], verdict: Verdict, report?: ReportKind) {
  const at = new Date().toISOString()
  state = { ...state }
  for (const id of ids) {
    state[id] = { id, verdict, report, at }
    push(id, verdict, report ?? '')
  }
  keep()
  emit()
}

export function undo(id: string) {
  state = { ...state }
  delete state[id]
  push(id, 'undo')
  keep()
  emit()
}

syncDecisions()

export function useDecisions() {
  return useSyncExternalStore(
    (f) => {
      subs.add(f)
      return () => subs.delete(f)
    },
    () => state,
  )
}

export function useBackend() {
  return useSyncExternalStore(
    (f) => {
      subs.add(f)
      return () => subs.delete(f)
    },
    () => backend,
  )
}

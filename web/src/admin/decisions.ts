import { useSyncExternalStore } from 'react'

// Reviewer decisions for the prototype. Kept in this browser until the review API exists;
// the UI says so wherever decisions are shown.
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

const KEY = 'tg.admin.decisions.v1'
let state: Record<string, Decision> = (() => {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}')
  } catch {
    return {}
  }
})()
const subs = new Set<() => void>()

export function decide(ids: string[], verdict: Verdict, report?: ReportKind) {
  const at = new Date().toISOString()
  state = { ...state }
  for (const id of ids) state[id] = { id, verdict, report, at }
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* kept in memory only */
  }
  subs.forEach((f) => f())
}

export function undo(id: string) {
  state = { ...state }
  delete state[id]
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* ignore */
  }
  subs.forEach((f) => f())
}

export function useDecisions() {
  return useSyncExternalStore(
    (f) => {
      subs.add(f)
      return () => subs.delete(f)
    },
    () => state,
  )
}

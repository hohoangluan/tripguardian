# Plan P8 — Web: a real Itinerary screen, talking to `python -m planning serve`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `/app/plan` screen (`Itinerary.tsx`) stops estimating a schedule in the browser and instead drives a real Planning session: variant tabs with a trade-off table, a day-by-day timeline built from the backend's actual `itinerary`/`travel_load`, a lodging panel, a free-text box wired to `POST .../turn` (SSE), and a "Chốt kế hoạch" button that calls `confirm`. `Feasibility.tsx`'s own confirm button creates that session (handing Planning the Decision Output it just got back, no second network hop), the same way `Understand.tsx` already creates a Decision session today.

**Architecture:** Mirror `web/src/user/pd/` (`types.ts`, `api.ts`, `decision.tsx`) into a new `web/src/user/planning/` with the same three-file shape: typed API responses, a thin `fetch`/SSE client, and a `PlanningProvider` + `usePlanning()` context that holds one session's `view`/`diff`/`error`/`busy` and exposes `act`, `say` (the turn), `reload`. `TripState` gains one field, `planningId`, exactly like `decisionId`. `Itinerary.tsx` is rewritten against `usePlanning()` the way `Feasibility.tsx` is already written against `useDecision()` — same provider pattern, same screen in `UserApp.tsx` (`/app/plan`), no routing change.

**Tech Stack:** React 18 + TypeScript (already in use), native `fetch`/`EventSource`/`ReadableStream`, Vite dev proxy. No new npm dependency.

**Spec:** `docs/specs/PLANNING_SPEC.md` (§API và web, bảng phase P8). Plan trước: `docs/plans/PLANNING_P7_AGENT.md` — **phải xong** (this plan's `turn` box calls `POST .../turn`, which P7 built; without P7 the box can still be wired, it will just always get the policy fallback's answer, same as Place Decision's own chat box behaves today when `AGENT_*` is unset). Blueprint, read directly (same product, same patterns, not imported — this is a different directory tree, not a module boundary, so copying its shape is the point): `web/src/user/pd/types.ts`, `web/src/user/pd/api.ts`, `web/src/user/pd/decision.tsx`, `web/src/user/screens/Feasibility.tsx`, `web/src/user/screens/Shortlist.tsx`'s `Chat` component, `web/vite.config.ts`.

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh. Chuỗi hiển thị người dùng tiếng Việt, giọng điệu và màu sắc giống các màn đã có (`verdict-head`, `btn`, `Page`, `Chip` trong `ui/bits`) — không tự chế hệ thống class CSS mới, tái dùng các class đã có trong `user.css` nơi hợp lý (`bubble`, `chips`, `pdchat*`, `tl*`, `daytabs`, `plan*`, `totals*`).
- **Không có bộ test tự động cho `web/`** (không `vitest`/`jest`, không file `*.test.ts*` nào trong `web/src`) — đã kiểm tra trực tiếp trước khi viết plan này. Mỗi task ở đây xác nhận bằng `tsc -b` (type check sạch) và một bước kiểm tay trên trình duyệt, không phải TDD unit test; đây đúng cách `pd/`, `tu/` đã được làm, không phải một ngoại lệ plan này tự đặt ra.
- `planning/api.ts` chỉ nói chuyện qua `/api/planning` (Vite proxy → `python -m planning serve`, cổng 8768). Không import gì từ `pd/` hay `tu/` (chúng là domain khác); các type trùng tên (`Diff`, `ActResult` shape) được định nghĩa lại trong `planning/types.ts`, như `pd/types.ts` đã tự định nghĩa `View`/`Action` riêng thay vì tái dùng `tu/types.ts`.
- `web/src/user/planner.ts` **không bị xoá** trong plan này — xem "Khác với spec" dưới đây.
- Không thêm dependency vào `package.json`.
- Mọi số hiển thị từ Planning (phút di chuyển, giá, robustness) đã có nhãn nguồn/ước lượng từ chính backend (`uncertainty`, `provenance`, `warnings` trong Plan Output) — UI chỉ hiển thị, không tự làm tròn hay tự suy ra một con số mới.

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| "`web/src/user/planner.ts` (ước lượng chạy trong trình duyệt của bản thử) **xoá**" | Giữ nguyên file `planner.ts`, chỉ gỡ import của nó khỏi `Itinerary.tsx` | `web/src/admin/screens/Sessions.tsx` cũng import `plan` từ `planner.ts` để xem trước lịch trình ước tính của một người dùng từ bản chụp `TripState` cục bộ của họ (`localTrip()`) -- một màn debug cho đội vận hành, **không có** phiên Planning sống nào để gọi (không có `planningId` trong bản chụp đó, và admin không có quyền tạo phiên hộ người dùng). Xoá `planner.ts` sẽ làm vỡ màn admin này; viết lại nó để không cần ước lượng phía client là việc ngoài phạm vi "Web: Itinerary thật" của P8. Để lại, gắn một dòng comment ở đầu file nói rõ nó chỉ còn dùng cho admin. |
| Không nói rõ `Itinerary.tsx` lấy `decision_output` từ đâu khi tạo phiên Planning | `Feasibility.tsx`'s `confirm(trip.decisionId)` đã trả về đúng Decision Output -- truyền thẳng nó làm `decision_output` khi tạo phiên Planning (`POST /api/planning/sessions {decision_output: out}`), không gọi lại `decision_session_id` (tránh một vòng HTTP thừa, và tránh phụ thuộc server Decision còn sống sau khi người dùng đã rời màn đó) | `Engine.create` đã nhận cả hai hình dạng (`decision | decision_session_id`, `PLANNING_P6_SESSION.md` Task 4); `decision_output` trực tiếp là đường ngắn nhất và không có downside. |
| "nút chốt" | `confirm()` điều hướng sang `/app/feedback` (route đã có, màn `Feedback.tsx` không đọc gì từ `trip`/`planner` nên không bị ảnh hưởng) | Giữ nguyên luồng điều hướng đã có từ trước P8; `Feedback.tsx` ngoài phạm vi plan này. |

## File Structure

| File | Việc |
|---|---|
| `web/vite.config.ts` | thêm proxy `/api/planning` → `http://127.0.0.1:8768` |
| `web/src/user/planning/types.ts` | mới: `View`, `Variant`, `LodgingCandidate`, `Action`, `ActResult`, `Diff`, `TurnHandlers`, `ProgressEvent` |
| `web/src/user/planning/api.ts` | mới: `createPlanning`, `loadPlanning`, `act`, `confirm`, `sendText`, `watchLodging`, `PlanningError` |
| `web/src/user/planning/planning.tsx` | mới: `PlanningProvider`, `usePlanning` |
| `web/src/user/trip.tsx` | thêm trường `planningId: string \| null` |
| `web/src/user/screens/Feasibility.tsx` | `go()` tạo thêm phiên Planning, lưu `planningId` |
| `web/src/user/screens/Itinerary.tsx` | viết lại: dùng `usePlanning()` thay `plan(trip)` |
| `web/src/user/planner.ts` | giữ, chỉ thêm một dòng comment "admin-only now" |
| `web/src/user/UserApp.tsx` | bọc màn `/app/plan` bằng `PlanningProvider` (như `/app/shortlist`.."/app/feasibility" đã bọc bằng `DecisionProvider`) |

---

### Task 1: Vite proxy + `planning/types.ts`

**Files:**
- Modify: `web/vite.config.ts`
- Create: `web/src/user/planning/types.ts`

**Interfaces:**
- Produces: every type the rest of this plan imports from `planning/types.ts`.

- [ ] **Step 1: Add the proxy**

In `web/vite.config.ts`, update the comment block and the `proxy` object:

```typescript
  // /api/decision: `python -m decision serve` (src/decision/server.py, Place Decision).
  // /api/planning: `python -m planning serve` (src/planning/server.py, Planning & Validation).
  // /api/trip: `python -m trip serve` (src/trip/server.py, Trip Understanding).
  // /api: `python -m corpus review` (src/corpus/review/server.py): decisions and gold labels.
  server: {
    proxy: {
      '/api/decision': 'http://127.0.0.1:8767',
      '/api/planning': 'http://127.0.0.1:8768',
      '/api/trip': 'http://127.0.0.1:8766',
      '/api': 'http://127.0.0.1:8765',
    },
  },
```

- [ ] **Step 2: Write the types**

Create `web/src/user/planning/types.ts` (shapes read directly off `src/planning/engine.py`'s `_view`/`_variant_dict`/`_build_base`, `src/planning/output.py`'s `build`, and `src/planning/session.py`'s `State`/`apply_act` -- not guessed):

```typescript
// Shapes of the Planning API (src/planning/engine.py, session.py, output.py, robustness.py, objectives.py).

export type DropReason = 'far' | 'crowded' | 'pricey' | 'dislike' | 'visited'
export type Pace = 'slow' | 'normal' | 'packed'

export interface ItineraryItem {
  kind: 'visit' | 'travel' | 'meal' | 'wait' | 'rest'
  start: string
  end: string
  place_id?: string
  name?: string
  from?: string
  to?: string
  mode?: string
  note?: string
}

export interface ItineraryDay {
  day: number // 1-based
  date: string | null
  weekday: string
  window: [string, string]
  method: string
  items: ItineraryItem[]
}

export interface TravelLoadDay {
  day: number
  travel_min: number
  wait_min: number
  longest_leg_min: number
}

export interface Robustness {
  level: 'Vững' | 'Khả thi' | 'Mong manh'
  label: string
  reasons: string[]
  scenarios: Record<string, unknown>[]
}

export interface VariantLodging {
  id: string | null
  name: string | null
  price_vnd: number | null
}

export interface Variant {
  id: string
  objective: string
  label: string
  score: [number, number]
  metrics: { travel_min: number; cost_vnd: number; cost_unknown: number; rain_exposed: number;
    exposure_unknown: number; repeats: number; pref_risk: number }
  itinerary: ItineraryDay[]
  travel_load: TravelLoadDay[]
  robustness: Robustness
  backups: Record<string, unknown>[]
  warnings: string[]
  lodging: VariantLodging
}

export interface LodgingCandidate {
  id: string
  name: string
  price_vnd: number | null
}

export interface Lodging {
  status: 'pending' | 'ready' | 'unavailable'
  candidates: LodgingCandidate[]
}

export interface SessionState {
  chosen_variant: string | null
  lodging_touched: boolean
  lodging_id: string | null
  lodging_point: Record<string, unknown> | null
  budget_override: number | null
  assignment: Record<string, number>
  order_override: Record<string, string[]>
  dropped: { place_id: string; reason: DropReason | null }[]
  locked: string[]
  pace_override: Pace | null
  objective_override: string | null
  day_window_override: Record<string, [number, number]>
  relaxed: { place_id: string; feature: string }[]
  last: string | null
}

export interface View {
  ok: boolean
  variants: Variant[]
  comparison: Record<string, unknown>[]
  warnings: string[]
  back_to_decision: { reason: string; places: string[] } | null
  lodging: Lodging
  itinerary: ItineraryDay[] | null
  travel_load: TravelLoadDay[] | null
  state: SessionState
}

export type Action =
  | { type: 'pick_variant'; id: string }
  | { type: 'pick_lodging'; id: string }
  | { type: 'clear_lodging' }
  | { type: 'set_lodging'; text: string }
  | { type: 'set_lodging_budget'; max_per_night: number | null }
  | { type: 'move_place'; place: string; day: number }
  | { type: 'reorder'; day: number; order: string[] }
  | { type: 'drop_place'; place: string; reason?: DropReason | null }
  | { type: 'add_from_backup'; place: string; day: number }
  | { type: 'swap'; place: string; with: string }
  | { type: 'lock_slot'; place: string }
  | { type: 'unlock'; place: string }
  | { type: 'set_pace'; level: Pace }
  | { type: 'set_objective'; name: string }
  | { type: 'set_day_window'; day: number; start: string; end: string }
  | { type: 'relax'; feature: string; place_id?: string; place_ids?: string[]; scope?: 'whole_trip' }
  | { type: 'undo' }
  | { type: 'redo' }

export interface Diff {
  scope: 'none' | 'relayout' | 'variant' | 'lodging_home' | 'lodging_fetch'
}

export interface ActResult {
  view: View
  diff: Diff
}

export interface TurnHandlers {
  say?: (d: { delta?: string; replace?: string }) => void
  view?: (d: ActResult) => void
  done?: () => void
  error?: (d: { message: string }) => void
}

export interface ProgressEvent {
  stage: string
  candidates: LodgingCandidate[]
  baseline_travel_min: number | null
}

export interface PlanOutput {
  variants: Record<string, unknown>[]
  chosen: string
  itinerary: ItineraryDay[]
  route: Record<string, unknown>[]
  lodging: { chosen: VariantLodging; candidates: LodgingCandidate[] }
  cost: Record<string, unknown>
  travel_load: TravelLoadDay[]
  reasons: string[]
  tradeoffs: Record<string, unknown>[]
  warnings: string[]
  uncertainty: Record<string, unknown>
  robustness: Robustness
  backups: Record<string, unknown>[]
  provenance: Record<string, unknown>
}
```

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc -b --noEmit` (or `npm run build` if a quick noEmit check is not configured)
Expected: no new errors (the file has no consumers yet, so it can only fail on its own syntax)

- [ ] **Step 4: Commit**

```bash
git add web/vite.config.ts web/src/user/planning/types.ts
git commit -m "feat(web): proxy /api/planning, and its response types"
```

---

### Task 2: `planning/api.ts`

**Files:**
- Create: `web/src/user/planning/api.ts`

**Interfaces:**
- Consumes: `./types`.
- Produces: `PlanningError`, `createPlanning(decisionOutput: unknown) -> Promise<{id, view}>`, `loadPlanning(id) -> Promise<{id, view}>`, `act(id, a: Action) -> Promise<ActResult>`, `confirm(id) -> Promise<PlanOutput>`, `sendText(id, text, h: TurnHandlers) -> Promise<void>`, `watchLodging(id, onEvent: (e: {event: string; data: unknown}) => void) -> () => void` (returns an unsubscribe function).

- [ ] **Step 1: Write the client**

Create `web/src/user/planning/api.ts` (the `sendText` body is copied from `pd/api.ts` verbatim -- POST + hand-rolled SSE reader, same reason given there: `EventSource` cannot POST):

```typescript
import type { Action, ActResult, PlanOutput, ProgressEvent, TurnHandlers, View } from './types'

const BASE = '/api/planning/sessions'

export class PlanningError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`Planning API ${status}: ${detail}`)
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = ((await res.json()) as { error?: string }).error ?? ''
    } catch {
      /* not JSON */
    }
    throw new PlanningError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const createPlanning = (decisionOutput: unknown) =>
  post(BASE, { decision_output: decisionOutput }).then((r) => json<{ id: string; view: View }>(r))

export const loadPlanning = (id: string) => fetch(`${BASE}/${id}`).then((r) => json<{ id: string; view: View }>(r))

export const act = (id: string, a: Action) => post(`${BASE}/${id}/act`, a).then((r) => json<ActResult>(r))

export const confirm = (id: string) => post(`${BASE}/${id}/confirm`, {}).then((r) => json<PlanOutput>(r))

// POST + server-sent events: EventSource cannot POST, so the stream is read by hand (as in pd/api.ts, tu/api.ts).
export async function sendText(id: string, text: string, h: TurnHandlers): Promise<void> {
  const res = await post(`${BASE}/${id}/turn`, { text })
  if (!res.ok || !res.body) throw new PlanningError(res.status, '')
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    let cut: number
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      dispatch(buf.slice(0, cut), h)
      buf = buf.slice(cut + 2)
    }
  }
}

function dispatch(block: string, h: TurnHandlers) {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!data) return
  const fn = (h as Record<string, ((d: unknown) => void) | undefined>)[event]
  fn?.(JSON.parse(data))
}

// GET + SSE: this route takes no body, so the native EventSource works (unlike /turn above).
export function watchLodging(id: string, onEvent: (e: { event: 'progress' | 'view' | 'done' | 'error'; data: unknown }) => void) {
  const es = new EventSource(`${BASE}/${id}/lodging/events`)
  const forward = (event: 'progress' | 'view' | 'done' | 'error') => (ev: MessageEvent) =>
    onEvent({ event, data: JSON.parse(ev.data) })
  es.addEventListener('progress', forward('progress') as EventListener)
  es.addEventListener('view', forward('view') as EventListener)
  es.addEventListener('done', forward('done') as EventListener)
  es.addEventListener('error', forward('error') as EventListener)
  es.onerror = () => es.close() // the server closes the stream itself once done/error fires; a transport drop just stops silently
  return () => es.close()
}

export type { ProgressEvent }
```

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc -b --noEmit`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add web/src/user/planning/api.ts
git commit -m "feat(web): planning API client -- create, act, confirm, turn (SSE), lodging events"
```

---

### Task 3: `PlanningProvider` / `usePlanning`

**Files:**
- Create: `web/src/user/planning/planning.tsx`

**Interfaces:**
- Consumes: `./api`, `./types`, `../trip` (`useTrip`, for `trip.planningId`).
- Produces: `PlanningProvider`, `usePlanning() -> {view, diff, lodgingEvent, error, busy, act, say, confirm, reload}`.

- [ ] **Step 1: Write the provider**

Create `web/src/user/planning/planning.tsx` (mirrors `pd/decision.tsx`; adds one thing `pd/decision.tsx` does not need -- subscribing to `watchLodging` once per session so the lodging panel updates itself when the background crawl finishes, per docs/specs/PLANNING_SPEC.md §Chỗ ở không làm người dùng chờ):

```typescript
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from './api'
import type { Action, Diff, PlanOutput, ProgressEvent, View } from './types'
import { useTrip } from '../trip'

interface PlanningCtx {
  view: View | null
  diff: Diff | null
  lodgingProgress: ProgressEvent | null
  error: string | null
  busy: boolean
  act: (a: Action) => Promise<void>
  say: (text: string, onSay: (soFar: string) => void) => Promise<void>
  confirm: () => Promise<PlanOutput | null>
  reload: () => void
}

const Ctx = createContext<PlanningCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ xếp lịch (python -m planning serve).'

export function PlanningProvider({ children }: { children: ReactNode }) {
  const { trip } = useTrip()
  const id = trip.planningId
  const [view, setView] = useState<View | null>(null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [lodgingProgress, setLodgingProgress] = useState<ProgressEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    setView(null)
    if (!id) return
    let live = true
    api.loadPlanning(id).then(
      (r) => {
        if (!live) return
        setView(r.view)
        setError(null)
      },
      () => {
        if (live) setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick])

  useEffect(() => {
    if (!id || view?.lodging.status !== 'pending') return
    const unsubscribe = api.watchLodging(id, (e) => {
      if (e.event === 'progress') setLodgingProgress(e.data as ProgressEvent)
      if (e.event === 'view') setView((e.data as { view: View }).view ?? (e.data as View))
    })
    return unsubscribe
  }, [id, view?.lodging.status])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return
      setBusy(true)
      try {
        const r = await api.act(id, a)
        setView(r.view)
        setDiff(r.diff)
        setError(null)
      } catch (e) {
        setError(e instanceof api.PlanningError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
      } finally {
        setBusy(false)
      }
    },
    [id],
  )

  const say = useCallback(
    async (text: string, onSay: (soFar: string) => void) => {
      if (!id) return
      setBusy(true)
      let acc = ''
      try {
        await api.sendText(id, text, {
          say: (d) => {
            acc = d.replace !== undefined ? d.replace : acc + (d.delta ?? '')
            onSay(acc)
          },
          view: (r) => {
            setView(r.view)
            setDiff(r.diff)
          },
          error: (d) => setError(d.message),
        })
      } catch {
        setError(OFFLINE)
      } finally {
        setBusy(false)
      }
    },
    [id],
  )

  const confirm = useCallback(async () => {
    if (!id) return null
    setBusy(true)
    try {
      const out = await api.confirm(id)
      setError(null)
      return out
    } catch (e) {
      setError(e instanceof api.PlanningError ? `Chưa chốt được: ${e.detail || e.status}` : OFFLINE)
      return null
    } finally {
      setBusy(false)
    }
  }, [id])

  return (
    <Ctx.Provider value={{ view, diff, lodgingProgress, error, busy, act, say, confirm, reload: () => setTick((t) => t + 1) }}>
      {children}
    </Ctx.Provider>
  )
}

export function usePlanning() {
  const c = useContext(Ctx)
  if (!c) throw new Error('usePlanning outside PlanningProvider')
  return c
}
```

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc -b --noEmit`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add web/src/user/planning/planning.tsx
git commit -m "feat(web): PlanningProvider -- one Planning session per trip, like DecisionProvider"
```

---

### Task 4: `TripState.planningId`, and wrap `/app/plan` in the provider

**Files:**
- Modify: `web/src/user/trip.tsx`
- Modify: `web/src/user/UserApp.tsx`

**Interfaces:**
- Produces: `TripState.planningId: string | null` (persisted the same way `decisionId` already is, via the existing `'set'` action -- no new `Action` variant needed).

- [ ] **Step 1: Add the field**

In `web/src/user/trip.tsx`:

```typescript
  decisionId: string | null // Place Decision session (src/decision); the backend holds the curation state
  planningId: string | null // Planning session (src/planning); the backend holds the schedule and its edits
```

and in `initialTrip`:

```typescript
  decisionId: null,
  planningId: null,
```

- [ ] **Step 2: Wrap the route**

In `web/src/user/UserApp.tsx`, find where `/app/plan` resolves to `<Itinerary />` (around the `base === '/app/plan'` branch) and where the existing `DecisionProvider` wraps the shortlist/feasibility routes; wrap this branch the same way:

```typescript
  else if (base === '/app/plan') screen = (
    <PlanningProvider>
      <Itinerary />
    </PlanningProvider>
  )
```

Add the import at the top:

```typescript
import { PlanningProvider } from './planning/planning'
```

(Match the exact variable name the file already uses for its render target -- read the surrounding 10 lines before editing, since this plan's Task 2 research only confirmed the route match, not the local variable name holding the JSX.)

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc -b --noEmit`
Expected: no new errors (both files compile; `Itinerary.tsx` is rewritten in Task 6, so until then it still imports `planner.ts` and ignores the new provider -- that is fine, the provider wrapping a screen that does not yet consume it is harmless)

- [ ] **Step 4: Commit**

```bash
git add web/src/user/trip.tsx web/src/user/UserApp.tsx
git commit -m "feat(web): trip.planningId, and wrap /app/plan in PlanningProvider"
```

---

### Task 5: `Feasibility.tsx` creates the Planning session on confirm

**Files:**
- Modify: `web/src/user/screens/Feasibility.tsx`

**Interfaces:**
- Consumes: `../planning/api` (`createPlanning`).
- Produces: `trip.planningId` set right after `trip.decisionId`'s own confirm succeeds.

- [ ] **Step 1: Update `go()`**

In `web/src/user/screens/Feasibility.tsx`, add the import:

```typescript
import { createPlanning } from '../planning/api'
```

Replace the body of `go()`:

```typescript
  const go = async () => {
    if (!trip.decisionId) return
    setSending(true)
    setMsg(null)
    try {
      const out = await confirm(trip.decisionId)
      const created = await createPlanning(out)
      dispatch({
        type: 'set',
        patch: {
          selected: out.confirmed.map((c) => c.id),
          locked: out.confirmed.filter((c) => c.role !== 'selected').map((c) => c.id),
          planningId: created.id,
        },
      })
      navigate('/app/plan')
    } catch {
      setMsg('Chưa xác nhận được, thử lại.')
    } finally {
      setSending(false)
    }
  }
```

(The old comment above this block, "The schedule screen is still the client prototype (Planning comes next); it reads the confirmed places," is now false -- delete it along with the code it was explaining.)

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc -b --noEmit`
Expected: no new errors

- [ ] **Step 3: Manual check**

With `python -m decision serve` and `python -m planning serve` both running (and `data/serving/places.json` present): walk Understand → Shortlist → Feasibility in the browser, reach a feasible status, click "chốt lịch" (whatever the confirm button's label is -- read the JSX around `go` before this step to quote it exactly). Expected: navigates to `/app/plan`; `localStorage`'s `tg.trip.v1` now has a non-null `planningId` (check via devtools).

- [ ] **Step 4: Commit**

```bash
git add web/src/user/screens/Feasibility.tsx
git commit -m "feat(web): confirming feasibility also creates the Planning session"
```

---

### Task 6: `Itinerary.tsx` — the real screen

**Files:**
- Modify: `web/src/user/screens/Itinerary.tsx`

**Interfaces:**
- Consumes: `../planning/planning` (`usePlanning`), `../planning/types`, `../planning/api` (`act`, `confirm` via the hook; no direct import needed beyond the hook itself), `../trip` (`useTrip`, only to read `planningId` for the empty-state guard -- the hook already does the fetching).
- Produces: nothing new (this is a leaf screen).

- [ ] **Step 1: Rewrite the screen**

Replace `web/src/user/screens/Itinerary.tsx` in full:

```typescript
import { type FormEvent, useLayoutEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { fmtDuration, fmtTime } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Page } from '../../ui/bits'
import { usePlanning } from '../planning/planning'
import type { ItineraryDay, Variant } from '../planning/types'
import { useTrip } from '../trip'

function toMin(hhmm: string) {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + (m || 0)
}

function VariantTabs({ variants, chosen, onPick }: { variants: Variant[]; chosen: string | null; onPick: (id: string) => void }) {
  return (
    <div className="daytabs" role="tablist">
      {variants.map((v) => (
        <button key={v.id} role="tab" aria-selected={chosen === v.id} className={chosen === v.id ? 'is-on' : ''} onClick={() => onPick(v.id)}>
          <b>{v.label}</b>
          <small>≈{fmtDuration(v.metrics.travel_min)} di chuyển cả chuyến</small>
          <span className={`robust robust--${v.robustness.level === 'Vững' ? 'ok' : v.robustness.level === 'Khả thi' ? 'mid' : 'thin'}`}>
            {v.robustness.level}
          </span>
        </button>
      ))}
    </div>
  )
}

function Trade({ variants }: { variants: Variant[] }) {
  if (variants.length < 2) return null
  return (
    <table className="totals totals--table">
      <thead>
        <tr>
          <th>Phương án</th>
          <th>Di chuyển</th>
          <th>Chi phí</th>
          <th>Độ vững</th>
        </tr>
      </thead>
      <tbody>
        {variants.map((v) => (
          <tr key={v.id}>
            <td>{v.label}</td>
            <td>≈{fmtDuration(v.metrics.travel_min)}</td>
            <td>{v.metrics.cost_unknown ? 'Một phần chưa có giá' : `${v.metrics.cost_vnd.toLocaleString('vi-VN')} đ`}</td>
            <td>{v.robustness.level}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function LodgingPanel() {
  const { view, lodgingProgress, act, busy } = usePlanning()
  if (!view) return null
  const status = view.lodging.status
  const candidates = status === 'pending' && lodgingProgress ? lodgingProgress.candidates : view.lodging.candidates
  const chosen = view.state.lodging_id
  return (
    <section className="plan__lodging">
      <h2>Chỗ ở</h2>
      {status === 'pending' && <p className="muted">Đang tìm chỗ ở gần lịch trình...</p>}
      {status === 'unavailable' && <p className="muted">Chưa tra được chỗ ở, lịch dùng điểm xuất phát làm neo.</p>}
      <ul className="lodging-list">
        {candidates.map((c) => (
          <li key={c.id}>
            <button className={chosen === c.id ? 'btn btn--small is-on' : 'btn btn--small btn--ghost'} disabled={busy} onClick={() => act({ type: 'pick_lodging', id: c.id })}>
              {c.name} {c.price_vnd ? `· ${c.price_vnd.toLocaleString('vi-VN')} đ/đêm` : '· chưa có giá'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function TurnBox() {
  const { say, busy } = usePlanning()
  const [text, setText] = useState('')
  const [reply, setReply] = useState<string | null>(null)
  const send = async (e: FormEvent) => {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy) return
    setText('')
    setReply('')
    await say(t, setReply)
  }
  return (
    <section className="pdchat">
      <form onSubmit={send}>
        <label className="pdchat__label" htmlFor="planchat">
          Nói với mình, ví dụ "Cà phê trước đi" hay "ngày 2 nhiều quá"
        </label>
        <div className="pdchat__row">
          <input id="planchat" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Gõ ở đây" />
          <button className="btn btn--small" disabled={busy || !text.trim()}>
            Gửi
          </button>
        </div>
      </form>
      {reply !== null && (
        <p className="bubble bubble--a" aria-live="polite">
          {reply || '…'}
        </p>
      )}
    </section>
  )
}

function DayView({ day }: { day: ItineraryDay }) {
  const timeline = useRef<HTMLOListElement>(null)
  useLayoutEffect(() => {
    if (story.reducedMotion || !timeline.current) return
    const ctx = gsap.context(() => {
      gsap.fromTo('.tl__rail', { scaleY: 0 }, { scaleY: 1, duration: 1.1, ease: 'power2.inOut', transformOrigin: 'top' })
      gsap.from('.tl__item', { opacity: 0, x: 16, duration: 0.5, stagger: 0.09, delay: 0.15, ease: 'power2.out' })
    }, timeline)
    return () => ctx.revert()
  }, [day])

  return (
    <ol className="tl" ref={timeline}>
      <span className="tl__rail" aria-hidden="true" />
      {day.items.map((it, i) => {
        if (it.kind === 'travel')
          return (
            <li className="tl__leg-row" key={i}>
              <Icon name="route" size={13} /> ≈{toMin(it.end) - toMin(it.start)} phút đi
            </li>
          )
        return (
          <li className="tl__item" key={i}>
            <span className="tl__time">{fmtTime(toMin(it.start))}</span>
            <span className="tl__dot tl__dot--stop" />
            <div className="tl__body">
              {it.place_id ? (
                <button className="link tl__name" onClick={() => navigate(`/app/place/${encodeURIComponent(it.place_id!)}`)}>
                  {it.name}
                </button>
              ) : (
                <span className="tl__name">{it.name ?? (it.kind === 'meal' ? 'Ăn (tự chọn)' : it.kind === 'rest' ? 'Nghỉ' : it.kind)}</span>
              )}
              <small>đến {fmtTime(toMin(it.end))}</small>
              {it.note && (
                <p className="tl__flag">
                  <Icon name="alert" size={13} /> {it.note}
                </p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function Itinerary() {
  const { trip } = useTrip()
  const { view, error, busy, act, confirm: confirmPlan } = usePlanning()
  const [dayIdx, setDayIdx] = useState(0)

  const variant = useMemo(() => view?.variants.find((v) => v.id === view.state.chosen_variant) ?? null, [view])
  const days = view?.itinerary ?? variant?.itinerary ?? []

  if (!trip.planningId)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có lịch trình. Xác nhận khả thi trước đã.</p>
          <button className="btn" onClick={() => navigate('/app/feasibility')}>
            Kiểm tra khả thi
          </button>
        </div>
      </Page>
    )

  if (!view) return <div className="loading">{error ?? 'Đang tải'}</div>

  if (!view.state.chosen_variant)
    return (
      <Page className="page--narrow">
        <header className="phead">
          <h1>Chọn một phương án</h1>
          <p>Mỗi phương án tối ưu một mục tiêu khác nhau.</p>
        </header>
        <VariantTabs variants={view.variants} chosen={null} onPick={(id) => act({ type: 'pick_variant', id })} />
        <Trade variants={view.variants} />
      </Page>
    )

  const d = days[dayIdx]

  const onConfirm = async () => {
    const out = await confirmPlan()
    if (out) navigate('/app/feedback')
  }

  return (
    <Page className="page--wide">
      <header className="phead phead--split">
        <div>
          <h1>Lịch trình</h1>
          <p>Giờ giấc và đường đi là ước tính.</p>
        </div>
      </header>

      <VariantTabs variants={view.variants} chosen={view.state.chosen_variant} onPick={(id) => act({ type: 'pick_variant', id })} />
      <Trade variants={view.variants} />

      <div className="daytabs" role="tablist">
        {days.map((x, i) => (
          <button key={x.day} role="tab" aria-selected={dayIdx === i} className={dayIdx === i ? 'is-on' : ''} onClick={() => setDayIdx(i)}>
            <b>Ngày {x.day}</b>
            {x.date && <small>{new Date(x.date).toLocaleDateString('vi-VN', { weekday: 'short', day: 'numeric', month: 'numeric' })}</small>}
          </button>
        ))}
      </div>

      {d && (
        <div className="plan">
          <div className="plan__left">
            <DayView day={d} />
            <dl className="totals totals--inline">
              <div>
                <dt>Di chuyển</dt>
                <dd>≈{fmtDuration(view.travel_load?.[dayIdx]?.travel_min ?? 0)}</dd>
              </div>
            </dl>
          </div>
          <LodgingPanel />
        </div>
      )}

      {view.warnings.length > 0 && (
        <ul className="warn-list">
          {view.warnings.map((w, i) => (
            <li key={i}>
              <Icon name="alert" size={13} /> {w}
            </li>
          ))}
        </ul>
      )}

      <TurnBox />

      {error && <p className="error">{error}</p>}

      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/feasibility')}>
          Quay lại kiểm tra
        </button>
        <button className="btn" disabled={busy} onClick={onConfirm}>
          Chốt kế hoạch này
        </button>
      </div>
    </Page>
  )
}
```

- [ ] **Step 2: Verify types compile**

Run: `cd web && npx tsc -b --noEmit`
Expected: no errors. Fix any mismatch against `../../data/store`'s real `fmtDuration`/`fmtTime` signatures and `../../ui/bits`'s real `Icon`/`Page` prop names before moving on -- this plan assumed they are unchanged from `Itinerary.tsx`'s previous version (Task 6's rewrite reuses them identically), but confirm by reading those two files if `tsc` disagrees.

- [ ] **Step 3: Manual walkthrough**

With both `python -m decision serve` and `python -m planning serve` running: go through Understand → Shortlist → Feasibility → confirm → land on `/app/plan`. Expected, in order:
1. If more than one variant objective was called for, a variant-picker screen with a trade-off table appears first; picking one reveals the day tabs.
2. The day timeline shows real place names, arrival times and travel legs from the backend, not the old client estimate.
3. The lodging panel shows "Đang tìm chỗ ở..." then switches to real candidates once the background crawl finishes (watch the Network tab for the `lodging/events` SSE connection closing).
4. Typing "a xa quá" (or any phrase naming a place actually in the plan, with the keyword "xa") in the turn box, with no `AGENT_*` configured, gets the policy's fixed reply and the place drops out of the timeline.
5. "Chốt kế hoạch này" navigates to `/app/feedback`.

- [ ] **Step 4: Commit**

```bash
git add web/src/user/screens/Itinerary.tsx
git commit -m "feat(web): Itinerary -- a real Planning session, variant tabs, lodging, the turn box"
```

---

### Task 7: Mark `planner.ts` admin-only, confirm nothing else regresses

**Files:**
- Modify: `web/src/user/planner.ts` (docstring comment only)

**Interfaces:**
- No interface change: `anchorOf`, `plan`, `rainBackup`, `Day`, `Stop`, `Plan`, `Conflict`, `Fix` all keep their exact current signatures (`web/src/admin/screens/Sessions.tsx` still imports `plan` from here unchanged).

- [ ] **Step 1: Update the file's header comment**

In `web/src/user/planner.ts`, replace line 1's comment:

```typescript
// Client-side trip estimate, now used only by the admin debug view (web/src/admin/screens/Sessions.tsx), which
// previews a user's trip from a local snapshot with no live Planning session to query. The real user-facing
// schedule is web/src/user/screens/Itinerary.tsx, backed by python -m planning serve (docs/specs/PLANNING_SPEC.md).
// Every number here is still an estimate and is labelled as one in the admin UI.
```

- [ ] **Step 2: Verify nothing else references the old behaviour**

Run: `cd web && npx tsc -b --noEmit` and `grep -rn "from '.*user/planner'" web/src` (or the Grep tool) to confirm the only remaining importer is `web/src/admin/screens/Sessions.tsx`.
Expected: `tsc` clean; exactly one importer left.

- [ ] **Step 3: Commit**

```bash
git add web/src/user/planner.ts
git commit -m "docs(web): mark planner.ts admin-only now that Itinerary uses the real Planning session"
```

---

## Execution note

This plan has no unit tests to run task by task (Global Constraints explains why: the `web/` tree has none). Each task's "Verify" step is `tsc -b --noEmit`, and Tasks 5-6 additionally need a manual browser walkthrough with `python -m decision serve` and `python -m planning serve` both running and `data/serving/places.json` present -- do not report either task done without that walkthrough (per this repo's own standing rule: "Type checking ... verifies code correctness, not feature correctness").

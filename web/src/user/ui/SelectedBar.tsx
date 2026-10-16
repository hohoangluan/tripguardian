import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useState } from 'react'
import { fmtMin, fmtVnd, info } from '../lib'
import { useDecision } from '../pd/decision'
import type { Conflict, Diff, Fix, PreviewVariant } from '../pd/types'
import { PlacePhoto } from './common'
import { openPlace } from './PlaceSheet'
import { Icon } from './icons'

export type BarLevel = 'building' | 'ready' | 'attention' | 'blocked'
const LEVEL_TEXT: Record<BarLevel, string> = { building: 'Đang xếp lịch…', ready: 'Lịch sẵn sàng', attention: 'Cần chú ý', blocked: 'Chưa đi được' }
const PLANNING_CAN_RESOLVE = new Set(['time', 'per_day', 'far_areas', 'time_windows', 'budget'])

// The cheapest schedule the background build found for the current selection.
const bestOf = (vs: PreviewVariant[]) => [...vs].sort((a, b) => a.metrics.travel_min - b.metrics.travel_min)[0] ?? null

// Feasibility is checked on every change by Decision; the schedule is built in the background (harness preview).
// Nothing here blocks picking places; the strip only opens when something needs the user.
export function useBar() {
  const { view, preview } = useDecision()
  const f = view?.feasibility
  const best = 'plan' in preview && preview.plan ? bestOf(preview.plan.variants) : null
  let level: BarLevel = 'ready'
  if (f?.status === 'infeasible') level = 'blocked'
  else if (f?.status === 'partial') level = 'attention'
  else if (preview.status === 'building') level = 'building'
  else if (preview.status === 'failed') level = 'attention'
  else if (preview.status === 'blocked') level = 'blocked'
  return { level, best, days: 'plan' in preview && preview.plan ? preview.plan.days : null, preview }
}

export function SelectedBar({ onRelax }: { onRelax: () => void }) {
  const { view, diff, act, busy, toPlan, error } = useDecision()
  const { level, best, days, preview } = useBar()
  const [open, setOpen] = useState(false)
  const [strip, setStrip] = useState(false)
  const [shown, setShown] = useState<Diff | null>(null)
  const f = view?.feasibility
  const key = f?.conflicts.map((c) => c.id).join('|') ?? ''
  useEffect(() => { setStrip(level === 'blocked') }, [key, level])
  useEffect(() => {
    if (!diff?.text) return
    setShown(diff)
    const t = setTimeout(() => setShown(null), 7000)
    return () => clearTimeout(t)
  }, [diff])
  if (!view || !f || (!view.selected.length && level !== 'blocked')) return null
  const t = f.totals
  const names = new Map([...view.groups.flatMap((g) => g.cards), ...view.unverified.cards].map((c) => [c.id, c.name]))
  // A chosen place may sit outside the groups on screen (a stay, a place from chat): the corpus still knows its name.
  const nameOf = (id: string) => names.get(id) ?? info(id)?.name ?? ''
  const failed = 'plan' in preview && preview.status === 'failed' ? preview.plan?.back_to_decision?.places ?? [] : []
  const needs = level === 'attention' || level === 'blocked'
  const overload = f.conflicts.length > 0 && f.conflicts.every((c) => PLANNING_CAN_RESOLVE.has(c.check))
  // Lựa chọn never stops the user: what needs attention is said above, the choice to go on stays theirs.
  const canGo = view.selected.length > 0 && !busy
  const nConflicts = f.conflicts.length + (failed.length ? 1 : 0)
  const go2plan = async () => { setOpen(false); await toPlan() }
  return (
    <>
      {needs && (
        <section className={`tg-notice is-${level}`} aria-label="Cần chú ý" aria-live="polite">
          <button type="button" className="tg-notice__head" onClick={() => setStrip((v) => !v)} aria-expanded={strip}>
            <Icon name={level === 'blocked' ? 'x' : 'warn'} size={18} />
            <b>{level === 'blocked' ? 'Bộ nơi này chưa đi được' : `${nConflicts || 1} chỗ cần chú ý`}</b>
            <span>{overload ? `Bạn đã chọn hơi nhiều nơi. Chọn chỗ ở rồi xem các hướng lập lịch.` : level === 'blocked' ? (f.known_days ? `Cần khoảng ${fmtMin(t.needed)}, chuyến đi có ${fmtMin(t.available)}` : 'Bỏ bớt vài nơi để lịch đi được') : 'Nên xem trước khi lập lịch. Bạn vẫn lập lịch được, quyết định là của bạn.'}</span>
            <Icon name={strip ? 'chevronDown' : 'chevronUp'} size={18} />
          </button>
          {strip && (
            <div className="tg-notice__body">
              {f.conflicts.map((c) => <ConflictRow key={c.id} c={c} names={names} busy={busy} onFix={(x) => (x.action ? act(x.action) : onRelax())} />)}
              {failed.length > 0 && (
                <div className="tg-conflict">
                  <div className="tg-conflict__top"><span className="tg-tag tg-tag--warn">Lịch</span><b>Chưa xếp được lịch với các nơi này</b></div>
                  <p className="tg-muted">Vướng ở: {failed.map((id) => names.get(id) ?? id).join(', ')}. Bỏ hoặc đổi nơi này thì lịch dựng lại ngay.</p>
                  <div className="tg-conflict__fixes">{failed.map((id) => <button key={id} type="button" className="tg-fix" disabled={busy} onClick={() => act({ type: 'drop', place_id: id })}><span><b>Bỏ {names.get(id) ?? id}</b><em>lịch được dựng lại ngay</em></span><Icon name="check" size={18} /></button>)}</div>
                </div>
              )}
              {overload && <p className="tg-muted">Đây mới là ước lượng ở bước chọn nơi. Planning sẽ xếp lịch thật và kiểm tra giờ mở cửa, di chuyển cùng các giới hạn khác.</p>}
              {f.conflicts.length === 0 && !failed.length && <p className="tg-muted">Bỏ bớt một vài nơi để lịch đi được.</p>}
              {view.wishlist.length > 0 && <p className="tg-notice__foot"><Icon name="bookmark" size={14} /> Để dành cho dịp khác: {view.wishlist.map((w) => w.name).join(', ')}</p>}
              <p className="tg-notice__foot"><Icon name="info" size={14} /> Mình không tự bỏ nơi bạn đã chọn; mỗi cách sửa ghi rõ cái giá.</p>
            </div>
          )}
        </section>
      )}
      <div className="tg-barwrap">
        {shown && (
          <p className="tg-diff" role="status"><Icon name="bolt" size={15} />{shown.text}.{shown.scope && <button type="button" className="tg-diff__undo" disabled={busy} onClick={() => act({ type: 'undo' })}>Hoàn tác</button>}</p>
        )}
        {error && <p className="tg-diff is-bad" role="alert"><Icon name="warn" size={15} />{error}</p>}
        <div className={`tg-bar is-${level}`} role="region" aria-label="Đã chọn">
          <button type="button" className="tg-bar__main" onClick={() => setOpen(true)} aria-haspopup="dialog">
            <span className="tg-bar__status"><i />{level !== 'ready' ? LEVEL_TEXT[level] : days ? `Lịch ${days} ngày sẵn sàng` : f.status === 'unknown' ? 'Chưa biết số ngày' : 'Đi kịp'}</span>
            {level === 'building' ? (
              <span className="tg-bar__skel" aria-busy="true"><span className="tg-skel" style={{ width: 120 }} /><span className="tg-skel" style={{ width: 90 }} /><span className="tg-skel" style={{ width: 110 }} /></span>
            ) : (
              <span className="tg-bar__stats">
                <span><b className="tg-mono">{t.places}</b> nơi</span>
                <span><b className="tg-mono">{fmtMin(t.visit)}</b> tham quan</span>
                <span>≈ <b className="tg-mono">{fmtMin(best ? best.metrics.travel_min : t.travel)}</b> đi lại</span>
                {best && <span>{best.metrics.cost_vnd ? <>~<b className="tg-mono">{fmtVnd(best.metrics.cost_vnd)}</b>{best.metrics.cost_unknown > 0 && <em> · một phần chưa có giá</em>}</> : <em>Chưa có giá</em>}</span>}
              </span>
            )}
            <Icon name="chevronUp" size={18} />
          </button>
          <button type="button" className="tg-btn tg-btn--primary" disabled={!canGo} onClick={go2plan}>
            {busy ? 'Đang xếp…' : 'Lập lịch'}<Icon name="arrow" size={18} />
          </button>
        </div>
      </div>
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="tg tg-overlay" />
          <Dialog.Content className="tg tg-listpanel" aria-describedby={undefined}>
            <header><Dialog.Title>Đã chọn {view.selected.length} nơi</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Thu gọn"><Icon name="chevronDown" size={20} /></Dialog.Close></header>
            <ul>
              {view.selected.map((id) => {
                const isLocked = view.locked.includes(id)
                const name = nameOf(id)
                if (!name) return null // never show a raw id
                return (
                  <li key={id}>
                    <PlacePhoto id={id} name={name} className="tg-listpanel__ph" />
                    <div><button type="button" className="tg-link tg-listpanel__name" onClick={() => { setOpen(false); openPlace(id) }}>{name}</button>
                      {view.chunks && view.chunks.length > 1 && <label className="tg-week-choice tg-faint">Tuần ghé <select aria-label={`Tuần ghé ${name}`} disabled={busy} value={view.chunk_assignments?.[id] ?? 0} onChange={(e) => act({ type: 'move_chunk', place_id: id, chunk: Number(e.target.value) })}>{view.chunks.map((chunk) => <option key={chunk.id} value={chunk.id}>Tuần {chunk.id + 1} · ngày {chunk.start_day}–{chunk.end_day} · {chunk.places.length} nơi</option>)}</select></label>}
                    </div>
                    <button type="button" className={`tg-icon-btn ${isLocked ? 'is-on' : ''}`} disabled={busy} onClick={() => act({ type: isLocked ? 'unlock' : 'lock', place_id: id })} aria-pressed={isLocked} aria-label={isLocked ? 'Bỏ khóa' : 'Khóa'}><Icon name={isLocked ? 'lock' : 'unlock'} size={18} /></button>
                    <button type="button" className="tg-icon-btn" disabled={busy} onClick={() => act({ type: 'drop', place_id: id })} aria-label={`Bỏ ${name}`}><Icon name="x" size={18} /></button>
                  </li>
                )
              })}
            </ul>
            {f.warnings.length > 0 && <ul className="tg-listpanel__warn">{f.warnings.map((w) => <li key={w}><Icon name="warn" size={14} />{w}</li>)}</ul>}
            <footer><span className="tg-faint">Giờ giấc và đường đi là ước tính.{f.known_days ? ` Chuyến đi có ${fmtMin(t.available)}.` : ' Chưa biết số ngày.'}</span><button type="button" className="tg-btn tg-btn--primary" disabled={!canGo} onClick={go2plan}>Chọn chỗ ở và lập lịch <Icon name="arrow" size={18} /></button></footer>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  )
}

// From the conflict to its fix in one step; each fix says what it costs. Physical limits have no "relax" row.
function ConflictRow({ c, names, busy, onFix }: { c: Conflict; names: Map<string, string>; busy: boolean; onFix: (f: Fix) => void }) {
  return (
    <div className="tg-conflict">
      <div className="tg-conflict__top"><span className={`tg-tag ${c.physical ? 'tg-tag--warn' : ''}`}>{c.physical ? 'Thời gian' : 'Giới hạn của bạn'}</span><b>{c.title}</b></div>
      <p className="tg-muted">{c.rule}{c.places.length ? ` · ${c.places.map((id) => names.get(id) ?? id).join(', ')}` : ''}</p>
      <div className="tg-conflict__fixes">
        {c.fixes.map((f) => (
          <button key={f.label} type="button" className="tg-fix" disabled={busy} onClick={() => onFix(f)}>
            <span><b>{f.label}</b>{f.effect && <em>{f.effect}</em>}</span><Icon name={f.action?.type === 'relax' || !f.action ? 'sliders' : 'check'} size={18} />
          </button>
        ))}
        {c.physical && <p className="tg-faint tg-conflict__note">Không có nút "nới" vì đây là giới hạn vật lý: ngày chỉ có chừng đó giờ.</p>}
      </div>
    </div>
  )
}

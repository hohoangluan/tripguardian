import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { fmtMin, fmtVnd, info, TRUST } from '../lib'
import * as pdApi from '../pd/api'
import { useDecision } from '../pd/decision'
import type { Action, LodgingChoice } from '../pd/types'
import type { LodgingCandidate } from '../planning/types'
import { toggleSaved, useUi } from '../store'
import { useTrip } from '../trip'
import { PlacePhoto, Trust } from '../ui/common'
import { Pager } from '../ui/Pager'
import { HeartFill, Icon } from '../ui/icons'
import { openPlace } from '../ui/PlaceSheet'

// The "Chỗ ở" tab of Lựa chọn: every served stay as a grid like the other groups, nothing asked of the user (Lịch trình
// suggests stays when the trip still has none). Planning orders them: around the chosen places first (taste, then
// location), the rest by taste and rating; one page at a time, like the other tabs. One lodging for the whole trip, and every
// day starts and ends there. A trip that already has one (told at Hiểu chuyến đi, or picked here) may change it, but
// only after the user confirms.

export const LODGING_TAB = 'lodging' // Lựa chọn's tab id for this panel
type Options = Awaited<ReturnType<typeof pdApi.lodgingOptions>>
const WAIT_MS = 400

export type LodgingList = { opts: Options | null; setOpts: React.Dispatch<React.SetStateAction<Options | null>>; failed: boolean }

// The first page of the list, held by Lựa chọn so the tab can show how many stays there are before it is opened. It
// follows the selection: asked again once the picks settle.
export function useLodgingList(enabled: boolean): LodgingList {
  const { trip } = useTrip()
  const { view } = useDecision()
  const [opts, setOpts] = useState<Options | null>(null)
  const [failed, setFailed] = useState(false)
  const first = useRef(true)
  const id = trip.decisionId
  const placesKey = view?.selected.join() ?? ''
  useEffect(() => {
    if (!id || !enabled) return
    let live = true
    setFailed(false)
    // the first list is asked for at once (the tab shows its count as soon as it can); later ones wait for the picks to settle
    const t = setTimeout(() => {
      pdApi.lodgingOptions(id).then((o) => { if (live) setOpts(o) }, () => { if (live) setFailed(true) })
    }, first.current ? 0 : WAIT_MS)
    first.current = false
    return () => { live = false; clearTimeout(t) }
  }, [id, placesKey, enabled])
  return { opts, setOpts, failed }
}

// The next pages of the list: the grid asks when its end comes into view, the disc when it nears the last stay.
export function useLodgingMore(list: LodgingList) {
  const { trip } = useTrip()
  const { opts, setOpts } = list
  const [loading, setLoading] = useState(false)
  const id = trip.decisionId
  const have = opts?.candidates.length ?? 0
  const more = Boolean(opts && opts.total !== undefined && have < opts.total)
  const load = () => {
    if (!id || !more || loading) return
    setLoading(true)
    pdApi.lodgingOptions(id, have).then((o) => setOpts((cur) => cur && { ...o, candidates: [...cur.candidates, ...o.candidates.filter((c) => !cur.candidates.some((x) => x.id === c.id))] }), () => {}).finally(() => setLoading(false))
  }
  return { more, loading, load }
}

// Choosing a stay: the first is taken at once; replacing or clearing one asks first. `dialog` is that question.
export function useLodgingChange() {
  const { view, act, busy } = useDecision()
  const [ask, setAsk] = useState<{ action: Action; to: string } | null>(null) // a change waiting for the user's yes
  const chosen = view?.lodging?.chosen ?? null
  const booked = view?.lodging?.booked ?? null
  const current = chosen?.text ?? booked?.text ?? null
  const change = (action: Action, to: string) => { if (current) setAsk({ action, to }); else void act(action) }
  const dialog = (
    <Dialog.Root open={Boolean(ask)} onOpenChange={(o) => !o && setAsk(null)}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg tg-overlay" />
        <Dialog.Content className="tg tg-sheet" aria-describedby={undefined}>
          <Dialog.Title>{ask?.action.type === 'clear_lodging' ? 'Bỏ nơi lưu trú đã chọn?' : 'Đổi nơi lưu trú?'}</Dialog.Title>
          <p className="tg-muted">
            {ask?.action.type === 'clear_lodging'
              ? <>Bạn đang ở <b>{current}</b>. {ask.to ? <>Mình quay về chỗ ở bạn đã có: <b>{ask.to}</b>.</> : 'Lịch sẽ chưa có chỗ ở để tính đường đi mỗi sáng và mỗi tối.'}</>
              : <>Bạn đang ở <b>{current}</b>. Đổi sang <b>{ask?.to}</b> thì mọi ngày bắt đầu và kết thúc ở chỗ mới, lịch được tính lại. Cả chuyến chỉ có một chỗ ở.</>}
          </p>
          <div className="tg-sheet__foot">
            <button type="button" className="tg-link" onClick={() => setAsk(null)}>Giữ chỗ cũ</button>
            <button type="button" className="tg-btn tg-btn--primary" disabled={busy} onClick={async () => { const a = ask?.action; setAsk(null); if (a) await act(a) }}>Xác nhận đổi</button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
  return { current, chosen, booked, change, setAsk, dialog }
}

export function LodgingPanel({ list }: { list: LodgingList }) {
  const { busy } = useDecision()
  const { trip } = useTrip()
  const { opts, failed } = list
  const top = useRef<HTMLElement>(null)
  const { current, chosen, booked, change, setAsk, dialog } = useLodgingChange()
  // Pages like the other tabs: page 1 is the list Lựa chọn holds; another page is asked for by its offset.
  const size = opts?.candidates.length || 18
  const total = opts?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / size))
  const [page, setPage] = useState(0)
  const [shown, setShown] = useState<LodgingCandidate[] | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => { setPage(0); setShown(null) }, [opts])
  const goPage = (n: number) => {
    const id = trip.decisionId
    if (!id || loading) return
    if (n === 1) { setPage(0); setShown(null); top.current?.scrollIntoView({ block: 'start' }); return }
    setLoading(true)
    pdApi.lodgingOptions(id, (n - 1) * size).then((o) => { setPage(n - 1); setShown(o.candidates); top.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, () => {}).finally(() => setLoading(false))
  }
  const cands = shown ?? opts?.candidates ?? []
  const tasteful = page === 0 && cands[0]?.fit?.length
  const pick = (c: LodgingCandidate) => change({ type: 'set_lodging', lodging: { kind: 'corpus', id: c.id } }, c.name)
  return (
    <section ref={top} className="tg-lod" aria-labelledby="tg-lod-h">
      <h2 id="tg-lod-h" className="tg-sr">Nơi lưu trú</h2>
      {chosen ? <Chosen c={chosen} busy={busy} back={booked?.text ?? null} onClear={() => setAsk({ action: { type: 'clear_lodging' }, to: booked?.text ?? '' })} />
        : booked && <div className="tg-lod__chosen" role="status"><Icon name="check" size={18} /><span>Bạn đã có chỗ ở: <b>{booked.text}</b>. Mọi ngày bắt đầu và kết thúc ở đây. Chọn chỗ khác bên dưới nếu muốn đổi.</span></div>}

      {failed ? (
        <p className="tg-lod__empty">Chưa tải được danh sách chỗ ở. Thử lại sau ít phút.</p>
      ) : !opts ? (
        <div className="tg-lod__grid" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <div key={i} className="tg-skel-card"><span className="tg-skel" /><div><span className="tg-skel tg-skel-line" /><span className="tg-skel tg-skel-line" style={{ width: '60%' }} /></div></div>)}</div>
      ) : !cands.length ? (
        <p className="tg-lod__empty">Chưa có chỗ ở nào trong dữ liệu khớp với chuyến này.</p>
      ) : (
        <div className="tg-grid">
          {cands.map((c, i) => <LodgingCard key={c.id} c={c} order={i % 18} top={i === 0 && !!tasteful} on={(chosen ? chosen.id : booked?.id) === c.id} swap={Boolean(current)} busy={busy} onPick={() => pick(c)} />)}
        </div>
      )}
      {cands.length > 0 && <Pager label="Nơi lưu trú" total={total} page={page} pages={pages} from={page * size + 1} to={page * size + cands.length} busy={loading} onPage={goPage} />}
      {dialog}
    </section>
  )
}

function Chosen({ c, busy, back, onClear }: { c: LodgingChoice; busy: boolean; back: string | null; onClear: () => void }) {
  return (
    <div className="tg-lod__chosen" role="status">
      <Icon name="check" size={18} />
      <span>Bạn ở <b>{c.text}</b>{c.price_vnd ? <> · <span className="tg-mono">{fmtVnd(c.price_vnd)}/đêm</span></> : null}. Mọi ngày bắt đầu và kết thúc ở đây.</span>
      <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} onClick={onClear}>{back ? 'Về chỗ đã có' : 'Bỏ chỗ này'}</button>
    </div>
  )
}

// "08/10" in Vietnam time.
function day(iso: string) {
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00+07:00` : iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit' })
}

// A lodging as a place card: the same markup as PlaceCard (ui/PlaceCard.tsx), so every group reads alike. The trip has
// one lodging: the first is added, any other replaces it, so once one is chosen the button of every other card says
// it swaps.
function LodgingCard({ c, order, top, on, swap, busy, onPick }: { c: LodgingCandidate; order: number; top: boolean; on: boolean; swap: boolean; busy: boolean; onPick: () => void }) {
  const p = info(c.id) // in the snapshot: photos and a detail sheet
  const saved = useUi((u) => u.saved.includes(c.id))
  const rating = p?.rating ?? c.rating
  const trade = c.tradeoffs?.[0]?.text ?? (c.unverified?.length ? `Chưa xác minh: ${c.unverified.join(', ')}` : null)
  const alerts = (c.tradeoffs ?? []).slice(1).map((t) => t.text)
  const loc = c.location
  return (
    <article className={`tg-pc ${on ? 'is-sel' : ''} is-stay`} style={{ '--i': order } as CSSProperties} data-place={c.id}>
      <div className="tg-pc__media">
        <button type="button" className="tg-pc__open" disabled={!p} onClick={(e) => openPlace(c.id, e.currentTarget.querySelector('figure'))} aria-label={p ? `Xem chi tiết ${c.name}` : undefined}>
          {p ? <PlacePhoto id={c.id} name={c.name} /> : <figure className="tg-lod__ph is-blank" aria-hidden="true"><Icon name="bed" size={32} /></figure>}
          <span className="tg-pc__shade" />
        </button>
        {c.category && <span className="tg-tag tg-tag--dark tg-pc__cat">{c.category}</span>}
        {top && <span className="tg-tag tg-pc__top" title="Hợp gu bạn nhất trong các chỗ ở">Hợp nhất</span>}
        <button type="button" className={`tg-pc__save ${saved ? 'is-on' : ''}`} onClick={() => toggleSaved(c.id, c.name)} aria-pressed={saved} aria-label={saved ? `Bỏ lưu ${c.name}` : `Lưu ${c.name}`}>{saved ? <HeartFill size={18} /> : <Icon name="heart" size={18} />}</button>
        {p?.photos[0]?.credit && <span className="tg-pc__credit">Ảnh: {p.photos[0].credit}</span>}
      </div>
      <div className="tg-pc__body">
        <div className="tg-pc__title">
          <h3>{c.name}</h3>
          <p className="tg-faint">{p?.area ?? c.area}{rating ? <> · <span className="tg-mono">★ {rating.toFixed(1)}</span></> : null}</p>
        </div>
        {c.why?.length ? (
          <ul className="tg-pc__why" aria-label="Vì sao phù hợp">
            {c.why.slice(0, 3).map((r) => <li key={r.text}><Icon name="check" size={15} />{r.text}</li>)}
          </ul>
        ) : <p className="tg-faint">Chưa có lý do rõ.</p>}
        {trade ? <p className="tg-pc__trade"><Icon name="warn" size={15} /><span><b>Đánh đổi:</b> {trade}</span></p> : <p className="tg-faint">Chưa thấy điều gì đáng ngại.</p>}
        {alerts.slice(0, 2).map((n) => <p key={n} className="tg-pc__alert"><Icon name="warn" size={14} />{n}</p>)}
        <div className="tg-pc__facts">
          {c.price_vnd ? <span className="tg-mono" title={c.price_at ? `Giá tham khảo trên Maps ngày ${day(c.price_at)}; kiểm lại khi đặt` : 'Giá tham khảo'}>{fmtVnd(c.price_vnd)}/đêm</span> : <span className="tg-faint">Chưa có giá</span>}
          {loc?.minutes != null && <span className="tg-mono" title="Ước tính">≈ {loc.minutes}′ từ {loc.center}</span>}
          {c.avg_min != null && <span className="tg-mono" title="Ước tính">≈ {fmtMin(c.avg_min)} tới các nơi đã chọn</span>}
          {c.confidence && <Trust level={TRUST[c.confidence.level]} why={c.confidence.reason} />}
        </div>
        <div className="tg-pc__act">
          {on ? (
            <button type="button" className="tg-btn tg-btn--sm tg-btn--soft" disabled aria-pressed="true"><Icon name="check" size={16} /> Đã chọn</button>
          ) : swap ? (
            <button type="button" className="tg-btn tg-btn--sm tg-btn--ghost" disabled={busy} onClick={onPick} aria-pressed="false"><Icon name="swap" size={16} /> Đổi sang chỗ này</button>
          ) : (
            <button type="button" className="tg-btn tg-btn--sm tg-btn--primary" disabled={busy} onClick={onPick} aria-pressed="false"><Icon name="plus" size={16} /> Thêm</button>
          )}
        </div>
      </div>
    </article>
  )
}

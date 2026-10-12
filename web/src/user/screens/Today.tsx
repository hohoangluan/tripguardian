import { useCallback, useEffect, useState } from 'react'
import { featureLabel, valueLabel } from '../../data/labels'
import { placeById } from '../../data/store'
import { navigate } from '../../router'
import { useAccount } from '../account'
import { track } from '../events'
import { info } from '../lib'
import { enablePush, pushSupported } from '../notify'
import { tripSummaries } from '../pd/api'
import type { TripSummary } from '../pd/types'
import { toast } from '../store'
import { calendarApply, calendarConnectHref, calendarPreview, companion, loadSuggestions, loadToday, searchPlaces, type CalChange, type CalPreview, type CalResult, type Nearby, type Stop, type Suggestions, type TodayView } from '../today'
import { useTrip } from '../trip'
import { ArtRoute, Busy, Empty, go, PlacePhoto } from '../ui/common'
import { Icon } from '../ui/icons'
import { Page, useTitle } from '../ui/Shell'

// Màn Hôm nay (docs/COMPANION.md, Role_Web §2.13). "Đã đến" is voluntary: a stop nobody checked in at just stays
// planned (unknown), never "missed". Before arriving the card shows the logistics and warnings; after, what to do here.
const SKIP: [string, string][] = [['crowded', 'Đông quá'], ['tired', 'Mệt rồi'], ['weather', 'Thời tiết'], ['far', 'Xa quá'], ['dislike', 'Không hợp'], ['other', 'Lý do khác']]
const DAY_TYPE: Record<string, string> = { weekday: 'ngày thường', weekend: 'cuối tuần' }
const BUCKET: Record<string, string> = { morning: 'buổi sáng', noon: 'buổi trưa', afternoon: 'buổi chiều', evening: 'buổi tối' }

export function Today() {
  useTitle('Hôm nay')
  const { trip } = useTrip()
  const params = new URLSearchParams(location.search)
  const id = params.get('journey') ?? (trip.planningId ? trip.journeyId : null)
  useEffect(() => { track('today_open') }, [])
  return id ? <TodayTrip id={id} focus={params.get('stop')} /> : <Pick />
}

function Pick() {
  const [list, setList] = useState<TripSummary[] | null>(null)
  useEffect(() => { tripSummaries().then((l) => setList(l.filter((t) => t.confirmed)), () => setList([])) }, [])
  if (!list) return <Page><Busy text="Đang tìm chuyến đã chốt…" /></Page>
  if (!list.length) return <Page><Empty art={<ArtRoute />} title="Chưa có chuyến nào đã chốt lịch" body="Chốt lịch trình xong, màn này đi cùng bạn trong chuyến: bấm Đã đến ở mỗi điểm để có gợi ý tại chỗ." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/trips')}>Xem chuyến của tôi</button>} /></Page>
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Hôm nay</p><h1>Chọn chuyến đang đi</h1></div></header>
      <div className="tg-td__pick">{list.map((t) => <button key={t.id} type="button" className="tg-card tg-td__pickc" onClick={() => navigate(`/app/today?journey=${t.id}`)}><b>Đà Lạt{t.days ? ` ${t.days} ngày` : ''}</b><span className="tg-muted">{t.start_date ?? 'Chưa chốt ngày'} · {t.places.length} nơi</span></button>)}</div>
    </Page>
  )
}

function TodayTrip({ id, focus }: { id: string; focus: string | null }) {
  const [view, setView] = useState<TodayView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [day, setDay] = useState<number | undefined>()
  const [here, setHere] = useState<string | null>(null)
  const [other, setOther] = useState(false)
  const [tight, setTight] = useState(false)
  const reload = useCallback((d?: number) => loadToday(id, d).then((v) => { setView(v); setError(null) }, (e: Error) => setError(e.message)), [id])
  useEffect(() => { void reload(day) }, [reload, day])
  // On a wide screen the last check-in reopens "Ở đây" beside the list; on a narrow one it is a sheet, opened by hand.
  useEffect(() => { if (view?.here && here === null && matchMedia('(min-width: 901px)').matches) setHere(view.here.place_id) }, [view?.here?.place_id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (focus) document.getElementById(`stop-${focus}`)?.scrollIntoView({ block: 'center' }) }, [focus, view === null])
  if (error) return <Page><Empty art={<ArtRoute />} title="Chưa mở được chuyến này" body="Chuyến cần có lịch đã chốt. Mở lại từ Chuyến của tôi." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/trips')}>Chuyến của tôi</button>} /></Page>
  if (!view) return <Page><Busy text="Đang mở lịch hôm nay…" /></Page>
  const shown = view.days.find((d) => d.day === view.day) ?? view.days[0]
  const act = async (op: 'checkin' | 'skip' | 'rate', payload: Record<string, unknown>) => {
    try {
      const out = await companion<{ place_id?: string }>(id, op, payload)
      if (op === 'checkin' && out.place_id) setHere(out.place_id)
      await reload(day)
    } catch { toast('Chưa lưu được, thử lại nhé') }
  }
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Hôm nay{view.trip.status === 'done' ? ' · chuyến đã xong' : ''}</p><h1>{shown?.date ? `Ngày ${shown.day} · ${new Date(shown.date + 'T00:00').toLocaleDateString('vi-VN', { weekday: 'long', day: 'numeric', month: 'numeric' })}` : `Ngày ${shown?.day ?? 1}`}</h1><p>Bấm <b>Đã đến</b> khi tới nơi để xem nên chơi gì ở đây và gần đây. Không bấm cũng không sao.</p></div>
        <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => setOther(true)}><Icon name="pin" size={16} /> Tôi đang ở nơi khác</button>
      </header>
      {view.days.length > 1 && <div className="tg-tabs" role="tablist" aria-label="Ngày">{view.days.map((d) => <button key={d.day} type="button" role="tab" aria-selected={d.day === view.day} className="tg-tab" onClick={() => setDay(d.day)}>Ngày {d.day}{d.day === view.today ? <b>hôm nay</b> : null}</button>)}</div>}
      <PushCard />
      {view.tight && view.tight.day === view.day && (
        <div className="tg-td__tight" role="status"><span>Phần còn lại hơi chật</span><button type="button" className="tg-link" onClick={() => setTight(true)}>Xem cách điều chỉnh</button></div>
      )}
      <div className={`tg-td ${here ? 'has-here' : ''}`}>
        <ol className="tg-td__stops" aria-label={`Các điểm ngày ${shown?.day}`}>
          {(shown?.stops ?? []).map((s) => <StopCard key={s.id} s={s} focus={s.id === focus} warnings={view.warnings} onAct={act} onOpen={() => setHere(s.place_id)} open={here === s.place_id} />)}
          {(shown?.stops.length ?? 0) === 0 && <li className="tg-muted">Ngày này chưa có điểm nào trong lịch.</li>}
        </ol>
        <aside className="tg-td__side">
          {here ? <HerePanel journey={id} place={here} onClose={() => setHere(null)} onChanged={() => reload(day)} day={view.day} /> : <TripSide view={view} journey={id} />}
        </aside>
      </div>
      {other && <OtherPlace onClose={() => setOther(false)} onPick={async (pid) => { setOther(false); await act('checkin', { place_id: pid }) }} />}
      {tight && view.tight && <Adjust journey={id} options={view.tight.options} late={view.tight.late_min} onClose={() => setTight(false)} onDone={() => { setTight(false); void reload(day) }} />}
    </Page>
  )
}

function StopCard({ s, focus, open, warnings, onAct, onOpen }: { s: Stop; focus: boolean; open: boolean; warnings: TodayView['warnings']; onAct: (op: 'checkin' | 'skip' | 'rate', p: Record<string, unknown>) => Promise<void>; onOpen: () => void }) {
  const [skipping, setSkipping] = useState(false)
  const p = info(s.place_id)
  const notes = warnings.filter((w) => s.name && w.text.includes(s.name))
  return (
    <li id={`stop-${s.id}`} className={`tg-card tg-stop is-${s.status} ${focus ? 'is-focus' : ''} ${open ? 'is-open' : ''}`}>
      <div className="tg-stop__time tg-mono">{s.arrive ?? '—'}<small>{s.leave ? `→ ${s.leave}` : ''}</small></div>
      <PlacePhoto id={s.place_id} className="tg-stop__ph" sizes="96px" />
      <div className="tg-stop__b">
        <h3>{s.name || p?.name}</h3>
        <p className="tg-faint">{[p?.category, p?.area, p?.hours ? `Mở ${p.hours}` : null].filter(Boolean).join(' · ')}</p>
        {notes.map((w) => <p key={w.code + w.text} className="tg-stop__warn"><Icon name="warn" size={14} /> {w.text}</p>)}
        {s.status === 'arrived' && <p className="tg-stop__state"><Icon name="check" size={14} /> Đã đến {s.arrived_at}</p>}
        {s.status === 'skipped' && <p className="tg-stop__state tg-faint">Đã bỏ qua</p>}
        <div className="tg-stop__act">
          {s.status === 'planned' && <>
            <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => onAct('checkin', { stop_id: s.id })}>Đã đến</button>
            <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" aria-expanded={skipping} onClick={() => setSkipping((x) => !x)}>Bỏ qua</button>
          </>}
          {s.status === 'arrived' && <>
            <button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={onOpen}>Ở đây có gì</button>
            <span className="tg-stop__rate" role="group" aria-label="Nơi này thế nào">
              <button type="button" className="tg-chip" aria-pressed={s.rating === 1} onClick={() => onAct('rate', { stop_id: s.id, value: s.rating === 1 ? null : 1 })}><Icon name="check" size={14} /> Hợp</button>
              <button type="button" className="tg-chip" aria-pressed={s.rating === -1} onClick={() => onAct('rate', { stop_id: s.id, value: s.rating === -1 ? null : -1 })}><Icon name="x" size={14} /> Không hợp</button>
            </span>
          </>}
        </div>
        {skipping && s.status === 'planned' && <div className="tg-stop__skip" role="group" aria-label="Vì sao bỏ qua (không bắt buộc)">{SKIP.map(([k, l]) => <button key={k} type="button" className="tg-chip" onClick={() => { setSkipping(false); void onAct('skip', { stop_id: s.id, reason: k }) }}>{l}</button>)}<button type="button" className="tg-chip tg-chip--dash" onClick={() => { setSkipping(false); void onAct('skip', { stop_id: s.id }) }}>Không nói</button></div>}
      </div>
    </li>
  )
}

function quoteOf(placeId: string, feature: string) {
  return placeById(placeId)?.features.find((f) => f.id === feature)?.quotes[0]?.text ?? null
}

function HerePanel({ journey, place, day, onClose, onChanged }: { journey: string; place: string; day: number; onClose: () => void; onChanged: () => void }) {
  const [s, setS] = useState<Suggestions | null>(null)
  const [similar, setSimilar] = useState(false)
  const [err, setErr] = useState(false)
  const [adding, setAdding] = useState<Nearby | null>(null)
  useEffect(() => { setS(null); loadSuggestions(journey, place, similar).then(setS, () => setErr(true)) }, [journey, place, similar])
  const p = info(place)
  const openPlace = (pid: string, kind: string) => {
    track('suggestion_open', { place_id: pid, kind })
    const q = new URLSearchParams(location.search)
    q.set('place', pid)
    navigate(`${location.pathname}?${q}`)
  }
  return (
    <section className="tg-card tg-here" aria-labelledby="tg-here-h">
      <header><div><p className="tg-kicker">Ở đây</p><h2 id="tg-here-h">{p?.name ?? 'Nơi bạn đang ở'}</h2></div><button type="button" className="tg-iconbtn" aria-label="Đóng" onClick={onClose}><Icon name="x" size={18} /></button></header>
      {err ? <p className="tg-muted">Chưa tải được gợi ý. Thử lại sau ít phút.</p> : !s ? <Busy text="Đang xem quanh đây…" /> : <>
        {s.play.length > 0 && <div className="tg-here__sec"><h3>Chơi gì ở đây</h3><ul>{s.play.map((f) => { const q = quoteOf(place, f.feature); return <li key={f.feature}><b>{featureLabel(f.feature)}{f.value !== 'present' ? `: ${valueLabel(f.value)}` : ''}</b>{f.wanted && <span className="tg-tag">bạn muốn</span>}{q && <q>{q}</q>}</li> })}</ul><button type="button" className="tg-link" onClick={() => openPlace(place, 'evidence')}>Xem ảnh, clip và đánh giá</button></div>}
        {s.practical.length > 0 && <div className="tg-here__sec"><h3>Lưu ý thực tế</h3><div className="tg-here__chips">{s.practical.map((f) => <span key={f.feature} className={`tg-chip ${f.status === 'UNCERTAIN' ? 'tg-chip--dash' : 'tg-chip--soft'}`}>{featureLabel(f.feature)}: {valueLabel(f.value)}{f.status === 'UNCERTAIN' ? ' (chưa chắc)' : ''}</span>)}</div></div>}
        {(s.timely.sunset || s.timely.crowd) && <div className="tg-here__sec"><h3>Theo giờ thực tế</h3>
          {s.timely.sunset && <p><Icon name="sun" size={15} /> Bình minh {s.timely.sunrise}, hoàng hôn {s.timely.sunset} hôm nay</p>}
          {s.timely.crowd && <p><Icon name="users" size={15} /> Google: {BUCKET[s.timely.crowd.bucket]} {DAY_TYPE[s.timely.crowd.day_type]} thường ở mức {s.timely.crowd.pct}% lúc đông nhất</p>}
        </div>}
        <div className="tg-here__sec"><h3>Gần đây</h3>
          <p className="tg-faint">{s.next ? `Còn khoảng ${s.budget_min} phút trước ${s.next.name} (${s.next.arrive}).` : 'Không còn điểm nào trong lịch hôm nay.'} Thời gian đi là ước tính.</p>
          <NearbyList items={s.nearby} onOpen={(n) => openPlace(n.place_id, 'nearby')} onAdd={setAdding} />
        </div>
        <div className="tg-here__sec">
          {!similar ? <button type="button" className="tg-link" onClick={() => setSimilar(true)}>Đông quá hoặc không như kỳ vọng? Xem nơi tương tự ở gần</button> : <><h3>Nơi tương tự ở gần</h3><NearbyList items={s.similar} onOpen={(n) => openPlace(n.place_id, 'similar')} onAdd={setAdding} /></>}
        </div>
      </>}
      {adding && <AddConfirm journey={journey} item={adding} day={day} onClose={() => setAdding(null)} onDone={() => { setAdding(null); onChanged() }} />}
    </section>
  )
}

function NearbyList({ items, onOpen, onAdd }: { items: Nearby[]; onOpen: (n: Nearby) => void; onAdd: (n: Nearby) => void }) {
  if (!items.length) return <p className="tg-muted">Chưa thấy nơi nào vừa thời gian và điều kiện của chuyến.</p>
  return (
    <ul className="tg-near">{items.map((n) => (
      <li key={n.place_id}>
        <PlacePhoto id={n.place_id} className="tg-near__ph" sizes="64px" />
        <div><b>{n.name}</b><span className="tg-faint">~{n.travel_min} phút · {n.open === null ? 'giờ mở chưa xác nhận' : 'đang mở'}{n.flags.length ? ` · chưa rõ: ${n.flags.map(featureLabel).join(', ')}` : ''}</span>
          {n.matches.length > 0 && <span className="tg-near__m">{n.matches.slice(0, 3).map((m) => featureLabel(m)).join(' · ')}</span>}</div>
        <div className="tg-near__act"><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => onOpen(n)}>Xem</button>{n.addable && <button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => onAdd(n)}>Thêm vào lịch</button>}</div>
      </li>
    ))}</ul>
  )
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="tg-td__scrim" role="presentation" onClick={onClose}>
      <div className="tg-card tg-td__modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header><h2>{title}</h2><button type="button" className="tg-iconbtn" aria-label="Đóng" onClick={onClose}><Icon name="x" size={18} /></button></header>
        {children}
      </div>
    </div>
  )
}

function AddConfirm({ journey, item, day, onClose, onDone }: { journey: string; item: Nearby; day: number; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const add = () => {
    setBusy(true)
    companion(journey, 'add', { place_id: item.place_id, day, confirmed: true }).then(() => { toast(`Đã thêm ${item.name}`); onDone() }, () => { setErr('Lịch chưa nhận được nơi này hôm nay (không vừa giờ hoặc điều kiện). Lịch cũ vẫn giữ nguyên.'); setBusy(false) })
  }
  return (
    <Modal title="Thêm vào lịch?" onClose={onClose}>
      <p>Thêm <b>{item.name}</b> vào ngày {day}. TripGuardian sẽ xếp lại phần còn lại của ngày; các điểm đã đến giữ nguyên.</p>
      {err && <p className="tg-auth__err" role="alert">{err}</p>}
      <div className="tg-td__btns"><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy} onClick={add}>{busy ? 'Đang xếp lại…' : 'Xác nhận thêm'}</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={onClose}>Thôi</button></div>
    </Modal>
  )
}

function Adjust({ journey, options, late, onClose, onDone }: { journey: string; options: { id: string; text: string }[]; late: number; onClose: () => void; onDone: () => void }) {
  const [pick, setPick] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const apply = () => {
    setBusy(true)
    companion(journey, 'adjust', { option_id: pick, confirmed: true }).then(() => { toast('Đã điều chỉnh lịch hôm nay'); onDone() }, () => { setErr(true); setBusy(false) })
  }
  return (
    <Modal title="Cách điều chỉnh phần còn lại" onClose={onClose}>
      <p className="tg-muted">Bạn tới muộn hơn lịch khoảng {late} phút. Chọn một cách nếu muốn; giữ nguyên cũng được.</p>
      <div className="tg-td__opts" role="radiogroup">{options.map((o) => <label key={o.id} className={`tg-td__opt ${pick === o.id ? 'is-on' : ''}`}><input type="radio" name="adj" checked={pick === o.id} onChange={() => setPick(o.id)} /> {o.text}</label>)}
        {options.length === 0 && <p className="tg-muted">Lịch không có phương án dự phòng cho ngày này. Bạn có thể bỏ qua một điểm ở danh sách.</p>}</div>
      {err && <p className="tg-auth__err" role="alert">Chưa đổi được lịch, lịch cũ vẫn giữ nguyên.</p>}
      <div className="tg-td__btns"><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={!pick || busy} onClick={apply}>{busy ? 'Đang xếp lại…' : 'Xác nhận đổi lịch'}</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={onClose}>Giữ nguyên</button></div>
    </Modal>
  )
}

function OtherPlace({ onClose, onPick }: { onClose: () => void; onPick: (id: string) => void }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<{ id: string; name: string; category: string | null }[]>([])
  useEffect(() => {
    if (q.trim().length < 2) return setHits([])
    const t = setTimeout(() => { searchPlaces(q).then(setHits, () => setHits([])) }, 250)
    return () => clearTimeout(t)
  }, [q])
  return (
    <Modal title="Bạn đang ở đâu?" onClose={onClose}>
      <label className="tg-auth__f"><span>Tên nơi</span><input className="tg-input" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ví dụ: Hồ Xuân Hương" /></label>
      <ul className="tg-td__hits">{hits.slice(0, 8).map((h) => <li key={h.id}><button type="button" onClick={() => onPick(h.id)}><b>{h.name}</b><span className="tg-faint">{h.category}</span></button></li>)}</ul>
      {q.trim().length >= 2 && hits.length === 0 && <p className="tg-muted">Chưa thấy nơi này trong dữ liệu Đà Lạt của TripGuardian.</p>}
    </Modal>
  )
}

// Asked only here, once the trip has a confirmed plan, and only when the user clicks; "Không, cảm ơn" is final.
function PushCard() {
  const [shown, setShown] = useState(() => {
    try { return pushSupported() && Notification.permission === 'default' && !localStorage.getItem('tg.push.answered') } catch { return false }
  })
  const [busy, setBusy] = useState(false)
  if (!shown) return null
  const done = () => { try { localStorage.setItem('tg.push.answered', '1') } catch { /* ok */ } setShown(false) }
  return (
    <section className="tg-card tg-push" aria-labelledby="tg-push-h">
      <h2 id="tg-push-h"><Icon name="bell" size={18} /> Nhận vài lời nhắc trong chuyến?</h2>
      <ul><li>Bản tin sáng: hôm nay đi đâu, mấy giờ</li><li>Giờ hoàng hôn ở nơi trong lịch</li><li>Chỗ hay hết chỗ, nên đặt trước</li></ul>
      <p className="tg-faint">Tối đa 3 lời nhắc mỗi ngày đi, không nhắn từ 22:00 đến 7:00. Tắt lúc nào cũng được.</p>
      <div className="tg-td__btns"><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy} onClick={async () => { setBusy(true); const r = await enablePush(); if (r === 'granted') toast('Đã bật thông báo'); else if (r === 'failed') toast('Chưa bật được thông báo trên trình duyệt này'); done() }}>Bật thông báo</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={done}>Không, cảm ơn</button></div>
    </section>
  )
}

function TripSide({ view, journey }: { view: TodayView; journey: string }) {
  return (
    <>
      <CalendarCard journey={journey} state={view.calendar} />
      {view.warnings.length > 0 && <section className="tg-card tg-td__warn"><h2>Cần để ý</h2><ul>{view.warnings.map((w) => <li key={w.code + w.text}>{w.text}</li>)}</ul></section>}
    </>
  )
}

const hm = (s?: string) => (s ? s.slice(11, 16) : '')

function CalendarCard({ journey, state }: { journey: string; state: TodayView['calendar'] }) {
  const account = useAccount()
  const [preview, setPreview] = useState<CalPreview | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<CalResult | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const next = `/app/today?journey=${journey}`
  useEffect(() => {
    if (state === 'drifted') calendarPreview(journey).then(setPreview, () => {})
    if (new URLSearchParams(location.search).get('calendar') === 'connected') show()
  }, [journey, state]) // eslint-disable-line react-hooks/exhaustive-deps
  function show() {
    setResult(null); setNote(null)
    calendarPreview(journey).then((p) => { setPreview(p); setOpen(true) }, () => toast('Chưa xem trước được lịch Google'))
  }
  const start = () => (account?.calendar ? show() : location.assign(calendarConnectHref(next)))
  const apply = async () => {
    if (!preview) return
    setBusy(true)
    try {
      const out = await calendarApply(journey, preview.preview_hash)
      if (out.stale) { setPreview(out.stale); setNote('Kế hoạch vừa đổi. Đây là bản xem trước mới, bạn xem lại rồi xác nhận nhé.') }
      else if (out.result) setResult(out.result)
    } catch { setNote('Google Calendar chưa nhận thay đổi. Lịch trong app vẫn nguyên.') }
    setBusy(false)
  }
  const n = preview?.changes.length ?? 0
  return (
    <section className="tg-card tg-cal" aria-labelledby="tg-cal-h">
      <h2 id="tg-cal-h"><Icon name="calendar" size={18} /> Google Calendar</h2>
      {state === 'drifted' ? <p>Lịch Google khác kế hoạch hiện tại{preview ? ` · ${n} thay đổi` : ''} <button type="button" className="tg-link" onClick={show}>Xem</button></p>
        : state === 'synced' ? <p className="tg-muted">Lịch Google đã khớp kế hoạch. Mỗi điểm một sự kiện, không có nhắc nhở.</p>
        : <><p className="tg-muted">Thêm lịch vào một lịch riêng tên TripGuardian. Mọi lần ghi đều hỏi bạn trước.</p><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={start}>Thêm vào Google Calendar</button></>}
      {open && preview && (
        <Modal title="Xem trước thay đổi trên Google Calendar" onClose={() => setOpen(false)}>
          {note && <p className="tg-td__note" role="status">{note}</p>}
          {result ? <>
            <p>{result.failed ? `Đã ghi ${result.applied} thay đổi. Còn ${result.not_done.length} chưa ghi được (${result.failed.error}). Bạn thử lại khi muốn.` : `Đã ghi ${result.applied} thay đổi vào Google Calendar.`}</p>
            <div className="tg-td__btns"><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => { setOpen(false); location.reload() }}>Xong</button></div>
          </> : <>
            {preview.calendar.create && <p>Tạo lịch mới <b>{preview.calendar.summary}</b>.</p>}
            {n === 0 ? <p className="tg-muted">Không có gì cần đổi.</p> : <ul className="tg-cal__list">{preview.changes.map((c) => <CalLine key={c.op + c.stop} c={c} />)}</ul>}
            <p className="tg-faint">Sự kiện không có nhắc nhở. TripGuardian không tự đồng bộ.</p>
            <div className="tg-td__btns"><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" disabled={busy || (n === 0 && !preview.calendar.create)} onClick={apply}>{busy ? 'Đang ghi…' : 'Xác nhận ghi vào Google Calendar'}</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => setOpen(false)}>Thôi</button></div>
          </>}
        </Modal>
      )}
    </section>
  )
}

function CalLine({ c }: { c: CalChange }) {
  const label = { create: 'Thêm', update: 'Đổi', delete: 'Xóa' }[c.op]
  return <li className={`is-${c.op}`}><span className="tg-tag">{label}</span> {c.after ? <><b>{c.after.summary}</b> <span className="tg-mono tg-faint">{c.after.start.dateTime.slice(5, 10)} {hm(c.after.start.dateTime)}–{hm(c.after.end.dateTime)}</span></> : <span className="tg-faint">một sự kiện không còn trong kế hoạch</span>}</li>
}

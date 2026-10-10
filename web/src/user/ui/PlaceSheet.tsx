import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { track } from '../events'
import { flushSync } from 'react-dom'
import { isNegative, signalPhrase } from '../../data/labels'
import { DAYS, mapsEmbed, openWindows, placeById, signal, useGallery, visible } from '../../data/store'
import type { Place, Video } from '../../data/types'
import { navigate } from '../../router'
import { DAY_NAMES, fmtClock, fmtRange, info, priceText, reducedMotion, TRUST } from '../lib'
import { useDecision } from '../pd/decision'
import type { Card, Claim } from '../pd/types'
import { DropSheet, useEditTicket } from '../screens/Explore'
import { toggleCmp, toggleSaved, useUi } from '../store'
import { go, Photo, Trust, Unconfirmed } from './common'
import { HeartFill, Icon } from './icons'

// docs/WEB.md §6: "Xem chi tiết" of a place. One sheet for the disc, the grid and the shared
// link page (/explore/place/:id). As a modal it lives in the URL (?place=<id>), so the browser's Back closes it.

const SLOTS: [string, string][] = [['early_morning', 'Sớm'], ['morning', 'Sáng'], ['noon', 'Trưa'], ['afternoon', 'Chiều'], ['evening', 'Tối']]
const TABS = [['overview', 'Tổng quan'], ['photos', 'Hình ảnh'], ['clips', 'Video'], ['plan', 'Gợi ý lịch trình'], ['reviews', 'Đánh giá']] as const
type Tab = (typeof TABS)[number][0]
const HERO = 'tg-hero' // view-transition-name shared by the photo that opened the sheet and the sheet's big photo
const EASE = 'cubic-bezier(.2,.8,.2,1)'

// The element the sheet flew out of (disc photo or card photo), to fly back to it and to give focus back.
let from: { photo: HTMLElement | null; focus: HTMLElement | null; rect: DOMRect | null } = { photo: null, focus: null, rect: null }

type VT = { startViewTransition?: (cb: () => void | Promise<void>) => { finished: Promise<void> } }
const canVT = () => typeof (document as unknown as VT).startViewTransition === 'function' && !reducedMotion()

const withPlace = (id: string | null) => {
  const q = new URLSearchParams(location.search)
  if (id) q.set('place', id)
  else q.delete('place')
  const s = q.toString()
  return location.pathname + (s ? `?${s}` : '')
}

// Opens the sheet over the current screen. `photo` is the image the user clicked from (shared-element animation).
export function openPlace(id: string, photo?: HTMLElement | null) {
  from = { photo: photo ?? null, focus: document.activeElement as HTMLElement | null, rect: photo?.getBoundingClientRect() ?? null }
  const show = () => {
    navigate(withPlace(id))
    history.replaceState({ tgSheet: 1 }, '', location.href)
  }
  if (photo && canVT()) {
    photo.style.viewTransitionName = HERO
    ;(document as unknown as VT).startViewTransition!(() => {
      photo.style.viewTransitionName = ''
      flushSync(show)
    })
  } else show()
}

// Back to the screen under the sheet: history back when the sheet pushed its own entry, else drop ?place.
function leave() {
  return new Promise<void>((done) => {
    if (history.state?.tgSheet) {
      addEventListener('popstate', () => setTimeout(done, 0), { once: true })
      history.back()
    } else {
      navigate(withPlace(null), { replace: true })
      done()
    }
  })
}

function closePlace(big: HTMLElement | null) {
  const back = from.photo && from.photo.isConnected ? from.photo : null
  const refocus = () => from.focus?.isConnected && from.focus.focus({ preventScroll: true })
  if (back && canVT()) {
    const t = (document as unknown as VT).startViewTransition!(async () => {
      await leave()
      back.style.viewTransitionName = HERO
    })
    t.finished.finally(() => { back.style.viewTransitionName = ''; refocus() })
    return
  }
  // No View Transitions: fly the big photo back by hand (FLIP), then leave.
  const r = back?.getBoundingClientRect()
  if (big && r && !reducedMotion()) {
    const b = big.getBoundingClientRect()
    big.closest('.tg-ps')?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, easing: EASE, fill: 'forwards' })
    big.animate([{ transform: 'none' }, { transform: flip(r, b) }], { duration: 300, easing: EASE, fill: 'forwards' }).finished.then(() => leave().then(refocus))
    return
  }
  leave().then(refocus)
}

const flip = (a: DOMRect, b: DOMRect) => `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`

// "07:00–17:00", "Mở cả ngày", "Đóng cửa hôm nay"; null when unknown (never assume open).
function hoursToday(p: Place) {
  const w = openWindows(p, DAYS[new Date().getDay()])
  if (w === null) return null
  if (!w.length) return 'Đóng cửa hôm nay'
  if (w.length === 1 && w[0][0] === 0 && w[0][1] >= 1440) return 'Mở cả ngày'
  return w.map(([a, b]) => `${fmtClock(a)}–${fmtClock(b)}`).join(', ')
}

// The 2–3 strongest verified things people say about the place, read as plain phrases ("Đồ ăn: tốt").
const highlights = (p: Place) =>
  visible(p).filter((f) => f.status === 'VERIFIED' && !isNegative(f.id, f.value)).sort((a, b) => b.n - a.n).slice(0, 3).map((f) => signalPhrase(f.id, f.value))

// The anonymous id this browser sends with reports: different people are counted by it (corpus.review.reports).
function reporterId() {
  try {
    let id = localStorage.getItem('tg.reporter.v1')
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem('tg.reporter.v1', id)
    }
    return id
  } catch {
    return crypto.randomUUID()
  }
}

// Modal over the current screen (`modal`), or the body of the shared-link page.
export function PlaceSheet({ id, modal = false }: { id: string; modal?: boolean }) {
  useEffect(() => { track('detail_open', { place_id: id, from: modal ? 'sheet' : 'page' }) }, [id, modal])
  const big = useRef<HTMLDivElement>(null)
  const close = () => closePlace(big.current)
  // FLIP fallback for the opening flight when the browser has no View Transitions.
  useLayoutEffect(() => {
    const el = big.current
    const a = from.rect
    if (!modal || !el || !a || canVT() || reducedMotion()) return
    el.animate([{ transform: flip(a, el.getBoundingClientRect()) }, { transform: 'none' }], { duration: 380, easing: EASE })
  }, [modal])
  const body = <SheetBody id={id} big={big} onClose={modal ? close : undefined} />
  if (!modal) return body
  return (
    <Dialog.Root open onOpenChange={(o) => !o && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg tg-psov" />
        <Dialog.Content className="tg tg-ps is-modal" aria-describedby={undefined} onCloseAutoFocus={(e) => e.preventDefault()}>{body}</Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function SheetBody({ id, big, onClose }: { id: string; big: React.RefObject<HTMLDivElement | null>; onClose?: () => void }) {
  const p = info(id)
  const snap = placeById(id)
  const { view, act, busy } = useDecision()
  const saved = useUi((u) => u.saved.includes(id))
  const cmp = useUi((u) => u.cmp.includes(id))
  const editTicket = useEditTicket()
  const [g, setG] = useState(0)
  const [tab, setTab] = useState<Tab>('overview')
  const [dropping, setDropping] = useState(false)
  const [report, setReport] = useState<'closed' | 'form' | 'sending' | 'sent' | 'error'>('closed')
  const [reportText, setReportText] = useState('')
  const [viewing, setViewing] = useState<number | null>(null) // the clip open in the TikTok-style viewer
  const tabsRef = useRef<HTMLDivElement>(null)
  const gallery = useGallery(id)
  useEffect(() => { setG(0); setTab('overview'); setViewing(null) }, [id])
  const Title = onClose ? Dialog.Title : 'h1'
  if (!p || !snap)
    return (
      <div className="tg-ps__none">
        {onClose && <Bar onClose={onClose} />}
        <Title>Không tìm thấy nơi này</Title>
        <p className="tg-muted">Nơi này chưa có trong dữ liệu Đà Lạt của mình, nên mình không nói gì về nó.</p>
        {!onClose && <button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/explore')}>Về danh sách gợi ý</button>}
      </div>
    )
  const card: Card | undefined = view ? [...view.groups.flatMap((c) => c.cards), ...view.unverified.cards].find((c) => c.id === id) : undefined
  const photos = gallery.length ? gallery : p.photos
  const shots = photos.length
  const others = photos.map((_, j) => j).filter((j) => j !== g).slice(0, 3)
  const quote = p.quotes[0]?.text
  const today = hoursToday(snap)
  const price = card?.price ?? priceText(p.price)
  const visit = card?.visit ? fmtRange(card.visit.short, card.visit.long) : null
  const rating = p.rating ? `${p.rating.toFixed(1).replace('.', ',')}${p.reviews ? ` · ${p.reviews.toLocaleString('vi-VN')} lượt` : ''}` : null
  const asOf = p.asOf ? p.asOf.split('-').reverse().join('/') : null
  const evidence = (c: Claim) => {
    const s = c.sid ? signal(snap, c.sid) : undefined
    return s ? `${Math.round(s.agreement * 100)}% trong ${s.n} người nhắc${s.freshnessDays !== null ? ` · mới nhất ${s.freshnessDays} ngày trước` : ''}` : null
  }
  const pick = (t: Tab) => {
    setTab(t)
    // The tab row sticks to the top; a tab chosen further down starts its content right under it.
    const el = tabsRef.current
    const sc = el?.closest('.tg-ps.is-modal') ?? null
    if (el && sc && el.getBoundingClientRect().top <= sc.getBoundingClientRect().top + 1) el.scrollIntoView({ block: 'start' })
  }
  const sendReport = async () => {
    const text = reportText.trim()
    if (!text) return
    setReport('sending')
    try {
      const r = await fetch('/api/harness/reports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ place_id: id, text, reporter: reporterId() }) })
      setReport(r.ok ? 'sent' : 'error')
      if (r.ok) setReportText('')
    } catch {
      setReport('error')
    }
  }
  const wd = p.crowd?.weekday
  const wk = p.crowd?.weekend
  const facts: [string, ReactNode][] = [
    ['Điểm Google', rating ?? <span className="tg-faint">Chưa có</span>],
    ['Giờ mở cửa hôm nay', today ?? <span className="tg-faint">Chưa rõ</span>],
    ['Thời gian tham quan', visit ?? <span className="tg-faint">Chưa có</span>],
  ]

  return (
    <>
      {onClose && <Bar onClose={onClose} />}
      <header className="tg-ps__head">
        <div className="tg-ps__lead">
          <p className="tg-ps__kick"><i />{[p.category, p.area].filter(Boolean).join(' · ')}</p>
          <Title className="tg-ps__name">{p.name}</Title>
          {quote && <p className="tg-ps__quote">“{quote}”<small>Trích từ đánh giá của người đã đến</small></p>}
          {highlights(snap).length > 0 && <p className="tg-ps__hl">{highlights(snap).join(' · ')}</p>}
          <dl className="tg-ps__facts">{facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          <div className="tg-ps__act">
            {card ? (
              card.chosen ? (
                <button type="button" className="tg-ps__cta is-on" disabled={busy || card.anchor} onClick={() => setDropping(true)} title={card.anchor ? 'Nơi bạn nói nhất định đến' : 'Bấm để bỏ khỏi hành trình'}><Icon name="check" size={18} /> Đã trong hành trình</button>
              ) : (
                <button type="button" className="tg-ps__cta" disabled={busy} onClick={() => act({ type: 'select', place_id: id })}>Thêm vào hành trình <Icon name="arrow" size={18} /></button>
              )
            ) : view ? (
              <span className="tg-faint tg-ps__out">Nơi này không nằm trong gợi ý của chuyến này. <button type="button" className="tg-link" onClick={editTicket}>Xem giới hạn</button></span>
            ) : null}
            <button type="button" className={`tg-disc__ic ${saved ? 'is-on' : ''}`} onClick={() => toggleSaved(id, p.name)} aria-pressed={saved} aria-label={saved ? 'Bỏ lưu' : 'Lưu'} title="Lưu">{saved ? <HeartFill size={18} /> : <Icon name="heart" size={18} />}</button>
            {card && (
              <Popover.Root>
                <Popover.Trigger asChild><button type="button" className="tg-disc__ic" aria-label="Thêm tùy chọn" title="Thêm"><Icon name="sliders" size={18} /></button></Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content className="tg tg-disc__menu tg-ps__menu" side="top" align="start" sideOffset={8} collisionPadding={16}>
                    <button type="button" disabled={busy} onClick={() => act({ type: card.locked ? 'unlock' : 'lock', place_id: id })} aria-pressed={card.locked}><Icon name={card.locked ? 'lock' : 'unlock'} size={16} />{card.locked ? 'Bỏ khóa nơi này' : 'Khóa nơi này'}</button>
                    <button type="button" onClick={() => toggleCmp(id)} aria-pressed={cmp}><Icon name="swap" size={16} />{cmp ? 'Bỏ khỏi so sánh' : 'Thêm vào so sánh'}</button>
                    {!card.chosen && <button type="button" onClick={() => setDropping(true)}><Icon name="x" size={16} />Bỏ nơi này</button>}
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            )}
          </div>
        </div>

        {/* The photo block of the disc: a big photo and three small ones; a small one becomes the big one. */}
        <div className="tg-disc__media tg-ps__media">
          <div className="tg-disc__big" ref={big} style={{ viewTransitionName: HERO }}>
            <Photo key={g} photo={photos[g]} alt={`${p.name}, ảnh ${g + 1} trên ${shots}`} className="tg-disc__ph is-fade" eager sizes="(max-width: 900px) 92vw, 640px" />
            {card?.chosen && <i className="tg-disc__chip"><Icon name="check" size={14} /> Đã chọn</i>}
            {shots > 0 && <span className="tg-disc__credit">Ảnh: {photos[g].credit} · {g + 1}/{shots}</span>}
          </div>
          {others.length > 0 && (
            <div className="tg-disc__thumbs">
              {others.map((j, k) => (
                <button key={j} type="button" className="tg-disc__thumb tg-ps__thumb" style={{ '--i': k } as React.CSSProperties} onClick={() => setG(j)} aria-label={`Xem ảnh ${j + 1} trên ${shots}`}>
                  <Photo photo={photos[j]} alt="" className="tg-disc__ph" eager />
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="tg-ps__tabs" role="tablist" aria-label="Thông tin về nơi này" ref={tabsRef}>
        {/* Video only when travellers' clips exist: one tap from anywhere in the sheet */}
        {TABS.filter(([k]) => k !== 'clips' || p.videos.length > 0).map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => pick(k)}>{l}{k === 'clips' && <small className="tg-mono"> {Math.min(6, p.videos.length)}</small>}</button>)}
      </div>

      <section className="tg-ps__pane" role="tabpanel">
        {tab === 'overview' && (
          <>
            <h3>Tổng quan</h3>
            <div className="tg-ps__ov">
              <dl className="tg-ps__rows">
                <div><dt>Điểm Google</dt><dd>{rating ?? <span className="tg-faint">Chưa có</span>}</dd></div>
                <div><dt>Giờ mở cửa hôm nay</dt><dd>{today ?? <span className="tg-faint">Chưa rõ</span>}{today && <> <Unconfirmed why="Mới có nguồn Google Maps, chưa có nguồn chính thức. Kiểm tra trước khi đi.">chưa xác nhận</Unconfirmed></>}</dd></div>
                <div><dt>Thời gian tham quan</dt><dd>{visit ? `≈ ${visit}` : <span className="tg-faint">Chưa có</span>}</dd></div>
                <div><dt>Giá</dt><dd>{price ? <>{price}{p.price && <span className="tg-faint"> · {p.price.reports} báo cáo</span>}</> : <span className="tg-faint">Chưa có thông tin</span>}</dd></div>
                <div><dt>Địa chỉ</dt><dd>{snap.address ?? <span className="tg-faint">Chưa có thông tin</span>}</dd></div>
                {card && <div><dt>Khoảng cách</dt><dd>{card.location.minutes !== null ? <>≈ {card.location.minutes} phút <span className="tg-faint">· ước tính từ {card.location.center}</span></> : <span className="tg-faint">Chưa có thông tin</span>}</dd></div>}
                <div><dt>Nguồn</dt><dd>{p.voices ? `${p.voices.toLocaleString('vi-VN')} người đã viết về nơi này` : 'Google Maps'}{asOf ? `, dữ liệu cập nhật ${asOf}` : ''}{card && <> <Trust level={TRUST[card.confidence.level]} why={card.confidence.reason} /></>}</dd></div>
              </dl>
              <div className="tg-ps__side">
                {shots > 0 && <div className="tg-ps__mini">{photos.slice(0, 4).map((ph, j) => <button key={ph.src} type="button" aria-pressed={j === g} onClick={() => setG(j)} aria-label={`Xem ảnh ${j + 1}`}><Photo photo={ph} alt="" className="tg-disc__ph" /></button>)}</div>}
                <div className="tg-minimap">
                  <iframe title={`Bản đồ ${p.name}`} src={mapsEmbed({ lat: p.lat, lng: p.lng }, 14)} loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
                  {p.mapsUrl && <a href={p.mapsUrl} target="_blank" rel="noreferrer" className="tg-link" onClick={() => track('outbound_click', { kind: 'maps', place_id: id })}>Mở trên Google Maps <Icon name="external" size={14} /></a>}
                </div>
              </div>
            </div>
            {card && (card.why.length > 0 || card.tradeoffs.length > 0) && (
              <div className="tg-ps__why">
                <h4>Vì sao hợp với chuyến của bạn</h4>
                <ul className="tg-why-list">
                  {card.why.map((w) => <li key={w.text}><Icon name="check" size={15} /><span>{w.text}{evidence(w) && <small className="tg-faint tg-mono"> · {evidence(w)}</small>}</span></li>)}
                  {card.tradeoffs.map((w) => <li key={w.text} className="tg-warn-t"><Icon name="warn" size={15} /><span><b>Đánh đổi:</b> {w.text}{evidence(w) && <small className="tg-faint tg-mono"> · {evidence(w)}</small>}</span></li>)}
                </ul>
              </div>
            )}
          </>
        )}

        {tab === 'photos' && (
          <>
            <h3>Hình ảnh</h3>
            {shots ? (
              <ul className="tg-ps__gal">{photos.map((ph, j) => <li key={ph.src}><Photo photo={ph} alt={`${p.name}, ảnh ${j + 1}`} className="tg-ps__gp" sizes="(max-width: 600px) 92vw, 260px" /><small>Ảnh: {ph.credit}</small></li>)}</ul>
            ) : <p className="tg-faint">Chưa có ảnh của nơi này.</p>}
          </>
        )}

        {tab === 'plan' && (
          <>
            <h3>Gợi ý lịch trình</h3>
            <dl className="tg-ps__rows">
              <div><dt>Giờ mở cửa</dt><dd>{snap.hoursText.length ? <ul>{DAYS.map((d, k) => [d, k] as const).slice(1).concat([[DAYS[0], 0]]).map(([d, k]) => <li key={d}><span className="tg-ps__day">{DAY_NAMES[k]}</span> {dayHours(snap, k)}</li>)}</ul> : <span className="tg-faint">Chưa có thông tin</span>}</dd></div>
              <div><dt>Nên dành</dt><dd>{visit ? `≈ ${visit}` : <span className="tg-faint">Chưa có</span>}</dd></div>
              <div><dt>Giá</dt><dd>{price ?? <span className="tg-faint">Chưa có thông tin</span>}</dd></div>
            </dl>
            {(wd || wk) ? (
              <div className="tg-crowd" aria-label="Độ đông theo buổi">
                <h4>Độ đông theo buổi</h4>
                {([['Ngày thường', wd], ['Cuối tuần', wk]] as const).map(([l, d]) => d && (
                  <div key={l} className="tg-crowd__row"><span>{l}</span>{SLOTS.filter(([k]) => k in d).map(([k, kl]) => <span key={k} className="tg-crowd__cell" title={`${kl}: ${d[k]}%`}><i style={{ height: `${d[k] ?? 0}%` }} /><small>{kl}</small></span>)}</div>
                ))}
              </div>
            ) : <p className="tg-faint">Chưa có số liệu độ đông theo buổi.</p>}
            <p className="tg-faint tg-ps__note"><Icon name="info" size={14} /> Ước tính: giờ đông của Google tính theo phần trăm so với giờ đông nhất của chính nơi này; thời gian tham quan và giờ giấc là ước tính, kiểm tra trước khi đi.</p>
          </>
        )}

        {tab === 'clips' && (
          <>
            <h3>Clip của người đã đến</h3>
            <ul className="tg-ps__clips">{p.videos.slice(0, 6).map((v, k) => <Clip key={v.id} v={v} onOpen={() => setViewing(k)} />)}</ul>
          </>
        )}

        {tab === 'reviews' && (
          <>
            <h3>Đánh giá</h3>
            {p.rating ? <p className="tg-ps__score"><b>{p.rating.toFixed(1).replace('.', ',')}</b>{p.reviews ? `${p.reviews.toLocaleString('vi-VN')} lượt đánh giá trên Google` : 'trên Google'}</p> : <p className="tg-faint">Chưa có điểm trên Google.</p>}
            {p.quotes.length > 0 && <ul className="tg-ps__rev">{p.quotes.map((q) => <li key={q.text}><q>{q.text}</q><small>{[sourceText(q.source), q.date?.split('-').reverse().join('/')].filter(Boolean).join(' · ')}</small></li>)}</ul>}
            {!p.quotes.length && <p className="tg-faint">Chưa có trích dẫn đánh giá cho nơi này; chỉ có thông tin cơ bản từ Google.</p>}
            <p className="tg-ps__foot"><button type="button" className="tg-link tg-link--quiet" onClick={() => setReport('form')}><Icon name="flag" size={14} /> Báo thông tin sai</button></p>
          </>
        )}
      </section>

      <DropSheet card={dropping && card ? card : null} onClose={() => setDropping(false)} />
      {viewing !== null && <ClipViewer videos={p.videos.slice(0, 6)} at={viewing} place={p.name} placeId={id} onAt={setViewing} onClose={() => setViewing(null)} />}
      <Dialog.Root open={report !== 'closed'} onOpenChange={(o) => !o && setReport('closed')}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay tg-ps__over" /><Dialog.Content className="tg tg-modal tg-ps__over" aria-describedby={undefined}>
          {report === 'sent' ? (
            <><Dialog.Title>Đã gửi.</Dialog.Title><p className="tg-muted">Báo cáo vào hàng chờ kiểm tra. Thông tin chỉ đổi khi đủ nhiều người khác nhau cùng báo một điều.</p><Dialog.Close className="tg-btn tg-btn--primary">Đóng</Dialog.Close></>
          ) : (
            <>
              <Dialog.Title>Thông tin nào của {p.name} chưa đúng?</Dialog.Title>
              <p className="tg-muted">Tả bằng lời của bạn. Mình chỉ đưa vào hàng đợi để kiểm tra, không đổi dữ liệu ngay.</p>
              <textarea className="tg-input" rows={4} maxLength={1000} value={reportText} onChange={(e) => setReportText(e.target.value)} placeholder="Ví dụ: quán đã đóng cửa vào thứ Hai" />
              {report === 'error' && <p className="tg-alert" role="alert"><Icon name="warn" size={15} /> Chưa gửi được, bạn thử lại nhé.</p>}
              <div className="tg-sheet__foot"><Dialog.Close className="tg-link">Hủy</Dialog.Close><button type="button" className="tg-btn tg-btn--primary" disabled={!reportText.trim() || report === 'sending'} onClick={sendReport}>{report === 'sending' ? 'Đang gửi…' : 'Gửi'}</button></div>
            </>
          )}
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </>
  )
}

// TikTok's own embedded player (credit and controls stay TikTok's). `preview`: no controls, muted, looping.
const playerSrc = (id: string, preview: boolean) =>
  `https://www.tiktok.com/player/v1/${id}?autoplay=1&rel=0&music_info=0&description=0${preview ? '&controls=0&progress_bar=0&play_button=0&volume_control=0&fullscreen_button=0&timestamp=0&loop=1' : '&loop=1'}`
// The player says when it is ready; a preview is then muted so hovering never makes a sound.
function useMuteWhenReady(frame: React.RefObject<HTMLIFrameElement | null>, on: boolean) {
  useEffect(() => {
    if (!on) return
    const f = (e: MessageEvent) => {
      const w = frame.current?.contentWindow
      if (!w || e.source !== w || !e.data?.['x-tiktok-player']) return
      if (e.data.type === 'onPlayerReady') {
        w.postMessage({ type: 'mute', 'x-tiktok-player': true }, '*')
        w.postMessage({ type: 'play', 'x-tiktok-player': true }, '*')
      }
    }
    addEventListener('message', f)
    return () => removeEventListener('message', f)
  }, [frame, on])
}

// A clip kept on our server (corpus tiktok clips), played by the browser itself.
const clipSrc = (id: string) => `/media/tiktok/${id}/video.mp4`

// A traveller's clip: its first frame; hovering a moment plays it muted in place, a click opens the viewer.
function Clip({ v, onOpen }: { v: Video; onOpen: () => void }) {
  const [hover, setHover] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const frame = useRef<HTMLIFrameElement>(null)
  useMuteWhenReady(frame, hover)
  useEffect(() => () => clearTimeout(timer.current), [])
  const desc = v.desc.replace(/#\S+/g, '').trim().slice(0, 120)
  const enter = () => { if (!reducedMotion()) timer.current = window.setTimeout(() => setHover(true), 280) }
  const leave = () => { clearTimeout(timer.current); setHover(false) }
  return (
    <li className="tg-ps__clip">
      <button type="button" className={`tg-ps__cplay ${hover ? 'is-live' : ''}`} onClick={onOpen} onMouseEnter={enter} onMouseLeave={leave} onFocus={enter} onBlur={leave} aria-label={`Xem clip của @${v.handle ?? 'tiktok'}`}>
        <img src={`/media/tiktok/${v.id}/frames/f1.jpg`} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.visibility = 'hidden' }} />
        {hover && (v.local
          ? <video src={clipSrc(v.id)} muted autoPlay loop playsInline preload="none" tabIndex={-1} aria-hidden="true" />
          : <iframe ref={frame} src={playerSrc(v.id, true)} title="" tabIndex={-1} aria-hidden="true" allow="autoplay; encrypted-media" />)}
        <span className="tg-ps__cbtn"><Icon name="play" size={26} /></span>
      </button>
      <b>@{v.handle ?? 'tiktok'}</b>
      {desc && <small className="tg-faint">{desc}</small>}
    </li>
  )
}

// The clips one at a time, like TikTok: a tall player in the middle, who posted it beside it, ↑ ↓ to the next one.
function ClipViewer({ videos, at, place, placeId, onAt, onClose }: { videos: Video[]; at: number; place: string; placeId: string; onAt: (i: number) => void; onClose: () => void }) {
  const v = videos[at]
  const n = videos.length
  const go = (d: number) => onAt((at + d + n) % n)
  const desc = v.desc.trim()
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="tg tg-cv__ov" />
        <Dialog.Content className="tg tg-cv" aria-describedby={undefined} onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); go(1) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); go(-1) }
        }}>
          <Dialog.Close className="tg-cv__x" aria-label="Đóng"><Icon name="x" size={22} /></Dialog.Close>
          <div className="tg-cv__stage">
            {v.local
              ? <video key={v.id} className="tg-cv__player" onPlay={() => track('evidence_play', { place_id: placeId, video_id: v.id })} src={clipSrc(v.id)} poster={`/media/tiktok/${v.id}/frames/f1.jpg`} controls autoPlay loop playsInline title={`Clip TikTok của @${v.handle ?? 'tiktok'}`} />
              : <iframe key={v.id} className="tg-cv__player" src={playerSrc(v.id, false)} title={`Clip TikTok của @${v.handle ?? 'tiktok'}`} allow="autoplay; fullscreen; encrypted-media; picture-in-picture" allowFullScreen />}
            <aside className="tg-cv__info">
              <p className="tg-cv__who"><i>{(v.handle ?? 't').slice(0, 1).toUpperCase()}</i><Dialog.Title asChild><b>@{v.handle ?? 'tiktok'}</b></Dialog.Title></p>
              <p className="tg-cv__place"><Icon name="pin" size={14} /> {place}</p>
              {desc && <p className="tg-cv__desc">{desc}</p>}
              <a href={v.url} target="_blank" rel="noreferrer" className="tg-cv__out" onClick={() => track('outbound_click', { kind: 'tiktok', place_id: placeId })}>Mở trên TikTok <Icon name="external" size={14} /></a>
              <p className="tg-cv__n tg-mono">{at + 1} / {n}</p>
            </aside>
          </div>
          {n > 1 && (
            <div className="tg-cv__nav">
              <button type="button" onClick={() => go(-1)} aria-label="Clip trước"><Icon name="chevronUp" size={24} /></button>
              <button type="button" onClick={() => go(1)} aria-label="Clip sau"><Icon name="chevronDown" size={24} /></button>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function Bar({ onClose }: { onClose: () => void }) {
  return (
    <div className="tg-ps__bar">
      <button type="button" className="tg-ps__back" onClick={onClose}><Icon name="arrowLeft" size={16} /> Quay lại gợi ý địa điểm</button>
      <button type="button" className="tg-ps__x" onClick={onClose} aria-label="Đóng"><Icon name="x" size={18} /></button>
    </div>
  )
}

// "gmaps_review" -> "Đánh giá Google Maps": where a quote was written, in words.
const sourceText = (s: string) => (s.startsWith('gmaps') ? 'Đánh giá Google Maps' : s.startsWith('tiktok') ? 'TikTok' : s)

function dayHours(p: Place, k: number) {
  const w = openWindows(p, DAYS[k])
  if (w === null) return <span className="tg-faint">chưa rõ</span>
  if (!w.length) return 'Đóng cửa'
  if (w.length === 1 && w[0][0] === 0 && w[0][1] >= 1440) return 'Mở cả ngày'
  return w.map(([a, b]) => `${fmtClock(a)}–${fmtClock(b)}`).join(', ')
}

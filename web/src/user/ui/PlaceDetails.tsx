import { Children, type ReactNode } from 'react'
import { featureLabel, isNegative, valueLabel } from '../../data/labels'
import { placeById, signal } from '../../data/store'
import type { DetailItem, DetailQuote, Fit, Place, TimeWindow } from '../../data/types'
import { fmtVnd } from '../lib'
import { Unconfirmed } from './common'
import { Icon } from './icons'

// docs/Role_Web_Functional_Design.md §6: the sections of the sheet's Tổng quan that answer what a visitor asks before
// going: known for, what it costs, what to order, when to go, the way there, bad weather, who it suits, what to bring,
// what to watch for, similar places. Every line says how many people said it and shows their words on request; a
// section with nothing says so ("Chưa có thông tin"), never a guess.

const TOD: Record<string, string> = { early_morning: 'sáng sớm', morning: 'buổi sáng', noon: 'buổi trưa', afternoon: 'buổi chiều', evening: 'buổi tối', night: 'ban đêm' }
const WEEKDAY: Record<string, string> = { mon: 'thứ Hai', tue: 'thứ Ba', wed: 'thứ Tư', thu: 'thứ Năm', fri: 'thứ Sáu', sat: 'thứ Bảy', sun: 'Chủ nhật' }
const UNIT: Record<string, string> = { person: '/người', group: '/nhóm', vehicle: '/xe', item: '/lượt' }
export const WHO_NAME: Record<string, string> = {
  solo: 'Đi một mình', partner: 'Người yêu, vợ chồng', friends: 'Bạn bè', kids: 'Trẻ nhỏ', baby: 'Em bé', parents: 'Bố mẹ, người lớn tuổi',
  pregnant: 'Bà bầu', wheelchair: 'Người đi xe lăn', pet: 'Thú cưng', coworkers: 'Đồng nghiệp', large_group: 'Đoàn đông',
}
const VERDICT: Record<Fit['value'], { text: string; icon: 'check' | 'warn' | 'info' }> = {
  good: { text: 'Hợp', icon: 'check' }, bad: { text: 'Không hợp', icon: 'warn' }, conditional: { text: 'Hợp có điều kiện', icon: 'info' },
}
const NONE = <span className="tg-faint">Chưa có thông tin</span>

const money = (v: number) => fmtVnd(v)
const months = (m: number[]) => `tháng ${m.join(', ')}`

function Quotes({ q }: { q?: DetailQuote[] }) {
  if (!q?.length) return null
  return (
    <details className="tg-ps__q">
      <summary>Lời người đã đi</summary>
      <ul>{q.map((x) => <li key={x.text}><q>{x.text}</q><small>{[x.source.startsWith('tiktok') ? 'TikTok' : x.source.startsWith('official') ? 'Trang chính thức' : 'Google Maps', x.date?.split('-').reverse().join('/')].filter(Boolean).join(' · ')}</small></li>)}</ul>
    </details>
  )
}

// One thing people said: its words, how many said it, and whether it is checked.
function Said({ it, tail }: { it: DetailItem; tail?: ReactNode }) {
  return (
    <span className="tg-ps__said">
      {it.text}{tail}
      <small className="tg-faint"> · {it.n} người nhắc</small>
      {it.status !== 'VERIFIED' && <> <Unconfirmed why="Mới có ít người nhắc, mình chưa kiểm tra kỹ.">chưa xác nhận</Unconfirmed></>}
      <Quotes q={it.quotes} />
    </span>
  )
}

const Items = ({ items }: { items: DetailItem[] }) => <ul className="tg-ps__list">{items.map((it) => <li key={it.text}><Said it={it} /></li>)}</ul>

function Section({ title, children }: { title: string; children: ReactNode }) {
  const rows = Children.toArray(children)  // drops the rows a section does not have and keys the rest
  return (
    <section className="tg-ps__sec">
      <h4>{title}</h4>
      {rows.length ? <dl className="tg-ps__rows">{rows}</dl> : <p>{NONE}</p>}
    </section>
  )
}

const Row = ({ k, children }: { k: string; children: ReactNode }) => <div><dt>{k}</dt><dd>{children}</dd></div>

// A served feature as a line: "Đẩy xe em bé được: không", with a warning mark when it is a downside (never colour alone).
function feature(p: Place, id: string): ReactNode {  // a plain function: a missing feature is null, so the section can see it has no rows
  const s = signal(p, id)
  if (!s || (s.status === 'UNCERTAIN' && s.n < 2)) return null
  const bad = isNegative(id, s.value)
  return (
    <Row key={id} k={featureLabel(id)}>
      <span className={bad ? 'tg-warn-t' : undefined}>{bad && <Icon name="warn" size={14} />} {s.value === 'present' ? 'Có' : valueLabel(s.value)}</span>
      <small className="tg-faint"> · {s.n} người nhắc</small>
      {s.status !== 'VERIFIED' && <> <Unconfirmed why="Chưa đủ người nhắc để chắc chắn.">chưa xác nhận</Unconfirmed></>}
    </Row>
  )
}

// "Nổi tiếng vì …" under the name.
export function KnownFor({ p }: { p: Place }) {
  const h = p.details?.known_for?.headline
  if (!h) return null
  return <p className="tg-ps__known"><Icon name="sparkle" size={15} /> Nổi tiếng vì <b>{h.text}</b><small> · {h.n} người nhắc</small></p>
}

function Cost({ p }: { p: Place }) {
  const c = p.details?.cost
  const rows: ReactNode[] = []
  if (c) {
    for (const [a, label] of [['adult', 'Vé người lớn'], ['child', 'Vé trẻ em'], ['senior', 'Vé người cao tuổi']] as const) {
      const e = c.entry[a]
      rows.push(e && <Row k={label}>{e.vnd === 0 ? 'Miễn phí' : money(e.vnd)} <small className="tg-faint">· {e.source === 'official' ? 'trang chính thức' : 'theo người đã đi'}</small></Row>)
    }
    rows.push(c.parking && <Row k="Gửi xe"><Said it={c.parking} tail={c.parking.amount_vnd ? <b> {money(c.parking.amount_vnd)}</b> : null} /></Row>)
    rows.push(c.extras.length > 0 && <Row k="Các khoản thêm"><ul className="tg-ps__list">{c.extras.map((x) => <li key={x.text}><Said it={x} tail={x.amount_vnd ? <b> {money(x.amount_vnd)}{UNIT[x.unit ?? ''] ?? ''}</b> : null} /></li>)}</ul></Row>)
    rows.push(c.per_party.length > 0 && <Row k="Giá theo xe, theo nhóm"><ul className="tg-ps__list">{c.per_party.map((x) => <li key={x.text}><Said it={x} tail={<b> {x.amount_vnd ? money(x.amount_vnd) : ''}{UNIT[x.unit ?? ''] ?? ''}{x.min_people ? `, từ ${x.min_people} người` : ''}</b>} /></li>)}</ul><small className="tg-faint">Đi ít người thì mỗi người chia nhiều hơn.</small></Row>)
    rows.push(c.total_vnd && <Row k="Tổng một người">{c.total_vnd.base === c.total_vnd.with_extras ? money(c.total_vnd.base) : `${money(c.total_vnd.base)} – ${money(c.total_vnd.with_extras)}`} <small className="tg-faint">· {c.kind === 'fact' ? 'theo trang chính thức' : 'ước tính, vé và gửi xe cộng các khoản thêm'}</small></Row>)
  }
  return <Section title="Tổng tiền">{rows}</Section>
}

function Eat({ p }: { p: Place }) {
  const d = p.details
  return (
    <Section title="Gọi món gì, làm gì">
      {[['Nên gọi', d?.order], ['Nên tránh', d?.avoid], ['Làm gì', d?.activity], ['Góc chụp ảnh', d?.photo_spot], ['Hay dùng để', d?.situation]]
        .map(([k, v]) => (v as DetailItem[] | undefined)?.length ? <Row key={k as string} k={k as string}><Items items={v as DetailItem[]} /></Row> : null)}
    </Section>
  )
}

function When({ p }: { p: Place }) {
  const t = p.details?.timing
  const win = (w: TimeWindow) => {
    const tod = Object.entries(w.by_time_of_day).sort((a, b) => b[1] - a[1]).map(([k]) => TOD[k] ?? k)
    return w.items.length ? <>{tod.length > 0 && <b>{tod.join(', ')}</b>}<Items items={w.items} /></> : null
  }
  const rows: ReactNode[] = t ? [
    t.best_time.items.length > 0 && <Row k="Giờ đẹp">{win(t.best_time)}</Row>,
    t.avoid_time.items.length > 0 && <Row k="Nên tránh giờ">{win(t.avoid_time)}</Row>,
    t.best_months.length > 0 && <Row k="Mùa đẹp">{months(t.best_months)}</Row>,
    t.avoid_months.length > 0 && <Row k="Mùa nên tránh"><span className="tg-warn-t"><Icon name="warn" size={14} /> {months(t.avoid_months)}</span></Row>,
    t.schedule.length > 0 && <Row k="Lịch cố định"><ul className="tg-ps__list">{t.schedule.map((x) => <li key={x.text}><Said it={x} tail={<b> {(x.days ?? []).map((d) => WEEKDAY[d] ?? d).join(', ')}</b>} /></li>)}</ul></Row>,
    t.last_entry && <Row k="Ngừng nhận khách"><b>{t.last_entry.time}</b> <small className="tg-faint">· {t.last_entry.source === 'official' ? 'trang chính thức' : 'theo người đã đi, hỏi lại trước khi tới'}</small></Row>,
  ] : []
  return <Section title="Giờ và mùa đẹp">{rows}</Section>
}

function Way({ p }: { p: Place }) {
  const d = p.details
  const walk = d?.walk_to_night_market_min
  return (
    <Section title="Đường đi">
      {['car_access', 'coach_access', 'night_road_risk', 'rough_road_access', 'steep_or_stairs', 'long_walk', 'stroller_access', 'rest_benches', 'parking'].map((id) => feature(p, id))}
      {d?.access?.length ? <Row k="Cách vào"><Items items={d.access} /></Row> : null}
      {walk != null ? <Row k="Chợ Đêm">≈ {walk} phút đi bộ <small className="tg-faint">· ước tính theo đường chim bay</small></Row> : null}
    </Section>
  )
}

const Weather = ({ p }: { p: Place }) => <Section title="Trời xấu">{['weather_exposed', 'fog_blocks_view', 'cold'].map((id) => feature(p, id))}</Section>

function WhoFits({ p, trip }: { p: Place; trip: string[] }) {
  const fit = p.details?.fit ?? {}
  const keys = Object.keys(fit).sort((a, b) => Number(trip.includes(b)) - Number(trip.includes(a)) || fit[b].n - fit[a].n)
  return (
    <Section title="Đi cùng ai">
      {keys.map((w) => {
        const f = fit[w]
        const v = VERDICT[f.value]
        return (
          <Row key={w} k={WHO_NAME[w] ?? w}>
            <span className={f.value === 'bad' ? 'tg-warn-t' : undefined}><Icon name={v.icon} size={14} /> <b>{v.text}</b></span>
            {trip.includes(w) && <small className="tg-ps__tag">Chuyến của bạn</small>}
            <small className="tg-faint"> · {f.n} người nhắc</small>
            {f.status !== 'VERIFIED' && <> <Unconfirmed why="Chưa đủ người nhắc để chắc chắn.">chưa xác nhận</Unconfirmed></>}
            {f.reasons.length > 0 && <ul className="tg-ps__list">{f.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            <Quotes q={f.quotes} />
          </Row>
        )
      })}
    </Section>
  )
}

function Prepare({ p }: { p: Place }) {
  const d = p.details
  return (
    <Section title="Chuẩn bị">
      {d?.bring?.length ? <Row k="Mang theo"><Items items={d.bring} /></Row> : null}
      {d?.booking?.length ? <Row k="Đặt chỗ, đặt vé"><Items items={d.booking} /></Row> : null}
      {['booking_needed', 'cash_only', 'heater', 'hot_water', 'breakfast', 'toilet_available', 'kids_play_area', 'pets'].map((id) => feature(p, id))}
    </Section>
  )
}

const Watch = ({ p }: { p: Place }) => <Section title="Cần cảnh báo">{['scam_stage', 'tourist_trap'].map((id) => feature(p, id))}</Section>

function Similar({ p, onOpen }: { p: Place; onOpen: (id: string) => void }) {
  const r = p.details?.relations
  const link = (ids: string[]) => ids.map((id) => placeById(id)).filter((x): x is Place => !!x).slice(0, 3)
    .map((x) => <button key={x.id} type="button" className="tg-link" onClick={() => onOpen(x.id)}>{x.name}</button>)
  const quieter = r ? link(r.quieter) : [], busier = r ? link(r.busier) : []
  return (
    <Section title="Nơi tương tự">
      {quieter.length > 0 && <Row k="Vắng hơn"><span className="tg-ps__chips">{quieter}</span></Row>}
      {busier.length > 0 && <Row k="Đông hơn"><span className="tg-ps__chips">{busier}</span></Row>}
    </Section>
  )
}

export function DetailsOverview({ p, trip, onOpen }: { p: Place; trip: string[]; onOpen: (id: string) => void }) {
  return (
    <div className="tg-ps__details">
      <Cost p={p} />
      <Eat p={p} />
      <When p={p} />
      <Way p={p} />
      <Weather p={p} />
      <WhoFits p={p} trip={trip} />
      <Prepare p={p} />
      <Watch p={p} />
      <Similar p={p} onOpen={onOpen} />
    </div>
  )
}

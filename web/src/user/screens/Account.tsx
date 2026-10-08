import { useEffect, useState } from 'react'
import { featureLabel, valueLabel } from '../../data/labels'
import { initialOf, signOut, useAccount } from '../account'
import { dateRange, info } from '../lib'
import { tripSummaries } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { TripSummary } from '../pd/types'
import { forgetTrip, toggleSaved, useUi } from '../store'
import { hasTrip, STEPS, stepOf, useTrip } from '../trip'
import { ArtCup, ArtHills, ArtRoute, Busy, Empty, go, Link, placeHref, PlacePhoto } from '../ui/common'
import { HeartFill, Icon } from '../ui/icons'
import { Page, useTitle } from '../ui/Shell'
import { useBegin } from './Discover'

const STAGE_STEP = { trip: 0, decision: 1, planning: 2 } as const
type Kind = 'building' | 'confirmed' | 'done'
const STATUS: Record<Kind, string> = { building: 'Đang lập', confirmed: 'Đã chốt', done: 'Đã đi' }

function kindOf(t: TripSummary): Kind {
  if (!t.confirmed) return 'building'
  if (!t.start_date) return 'confirmed'
  const end = new Date(t.start_date + 'T00:00')
  end.setDate(end.getDate() + (t.days ?? 1))
  return end < new Date() ? 'done' : 'confirmed'
}

// Journeys this browser started (store.trips); the server answers with one summary line each.
export function Trips() {
  useTitle('Chuyến của tôi')
  const ids = useUi((u) => u.trips)
  const { dispatch } = useTrip()
  const begin = useBegin()
  const [list, setList] = useState<TripSummary[] | null>(null)
  const [err, setErr] = useState(false)
  const [tab, setTab] = useState<Kind>('building')
  useEffect(() => {
    tripSummaries(ids).then((l) => {
      setList(l)
      const first = (['building', 'confirmed', 'done'] as const).find((k) => l.some((t) => kindOf(t) === k))
      if (first) setTab(first)
    }, () => setErr(true))
  }, [ids.join()]) // eslint-disable-line react-hooks/exhaustive-deps
  const open = (t: TripSummary, to?: string) => {
    dispatch({ type: 'reset' })
    dispatch({ type: 'set', patch: { journeyId: t.id, decisionId: t.stage === 'trip' ? null : t.id, planningId: t.stage === 'planning' ? t.id : null } })
    go(to ?? STEPS[STAGE_STEP[t.stage]].path)
  }
  const shown = (list ?? []).filter((t) => kindOf(t) === tab)
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Chuyến của tôi</p><h1>Chuyến đi của bạn</h1><p>Các chuyến bạn bắt đầu trên trình duyệt này.</p></div><button type="button" className="tg-btn tg-btn--primary" onClick={() => begin({ startWith: 'nothing', startText: null })}><Icon name="plus" size={18} /> Tạo chuyến đi</button></header>
      <div className="tg-tabs" role="tablist" aria-label="Trạng thái chuyến">
        {([['building', 'Đang lên kế hoạch'], ['confirmed', 'Sắp tới'], ['done', 'Đã hoàn thành']] as const).map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className="tg-tab" onClick={() => setTab(k)}>{l}{list && <b>{list.filter((t) => kindOf(t) === k).length}</b>}</button>)}
      </div>
      {err ? <Empty art={<ArtHills />} title="Chưa tải được danh sách chuyến" body="Máy chủ hành trình chưa trả lời. Thử lại sau ít phút." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => location.reload()}>Thử lại</button>} />
        : !list ? <Busy text="Đang tải các chuyến…" />
        : shown.length === 0 ? (
          <Empty art={tab === 'done' ? <ArtCup /> : <ArtRoute />} title={tab === 'building' ? 'Chưa có chuyến nào đang lập' : tab === 'confirmed' ? 'Chưa có chuyến sắp tới' : 'Chưa có chuyến nào hoàn thành'} body={tab === 'done' ? 'Đi xong chuyến đầu, nó sẽ nằm ở đây.' : 'Bắt đầu bằng một câu: bạn muốn đi Đà Lạt thế nào?'} action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/')}>Về Khám phá</button>} />
        ) : (
          <div className="tg-trips">
            {shown.map((t) => {
              const k = kindOf(t)
              const step = STAGE_STEP[t.stage]
              return (
                <article key={t.id} className="tg-trip">
                  {t.places[0] ? <PlacePhoto id={t.places[0]} className="tg-trip__ph" /> : <div className="tg-trip__ph tg-hero__img" aria-hidden="true" />}
                  <div className="tg-trip__body">
                    <span className={`tg-tag ${k === 'building' ? 'tg-tag--warn' : ''}`}>{STATUS[k]}</span>
                    <h2>Đà Lạt{t.days ? ` ${t.days} ngày` : ''}</h2>
                    <p className="tg-mono tg-muted">{[dateRange(t.start_date, t.days) ?? 'Chưa chốt ngày', t.people ? `${t.people} người` : null, `${t.places.length} nơi`].filter(Boolean).join(' · ')}</p>
                    {k === 'building' && <div className="tg-prog" aria-label={`Bước ${step + 1} trên ${STEPS.length}`}>{STEPS.map((s, i) => <span key={s.id} className={i < step ? 'is-done' : i === step ? 'is-now' : ''}><i />{s.label}</span>)}</div>}
                    <div className="tg-trip__act">
                      {k === 'building' && <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => open(t)}>Đi tiếp <Icon name="arrow" size={16} /></button>}
                      {k === 'confirmed' && <><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => open(t, '/plan')}>Xem lịch</button><button type="button" className="tg-link" onClick={() => open(t, '/plan')}>Sửa lại</button></>}
                      {k === 'done' && <><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => open(t, '/plan')}>Xem lại lịch</button><button type="button" className="tg-link" onClick={() => open(t, '/done')}>Phản hồi</button></>}
                      <button type="button" className="tg-link tg-link--quiet" onClick={() => forgetTrip(t.id)}>Ẩn khỏi danh sách</button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
    </Page>
  )
}

const GROUPS: [string, string][] = [['all', 'Tất cả'], ['sight', 'Tham quan & thiên nhiên'], ['food', 'Ăn uống & cà phê'], ['shop', 'Mua sắm']]

export function Saved() {
  useTitle('Đã lưu')
  const saved = useUi((u) => u.saved)
  const { view, act, busy } = useDecision()
  const [f, setF] = useState('all')
  const cards = new Map(view?.groups.flatMap((g) => g.cards).map((c) => [c.id, c]) ?? [])
  const items = saved.filter((id) => f === 'all' || info(id)?.group === f)
  const count = (k: string) => saved.filter((id) => k === 'all' || info(id)?.group === k).length
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Đã lưu</p><h1>Địa điểm bạn đã lưu</h1><p>Lưu trên trình duyệt này. Nơi đã lưu không tự vào lịch; thêm vào chuyến khi nơi đó nằm trong gợi ý.</p></div></header>
      <div className="tg-tabs" role="tablist" aria-label="Nhóm">
        {GROUPS.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={f === k} className="tg-tab" onClick={() => setF(k)}>{l}<b>{count(k)}</b></button>)}
      </div>
      {items.length === 0 ? <Empty art={<ArtCup />} title="Chưa lưu nơi nào" body="Bấm trái tim trên thẻ địa điểm để lưu lại, rồi thêm vào chuyến khi cần." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go(view ? '/explore' : '/')}>{view ? 'Xem gợi ý' : 'Về Khám phá'}</button>} /> : (
        <div className="tg-saved">
          {items.map((id) => {
            const p = info(id)
            const c = cards.get(id)
            return (
              <article key={id} className="tg-sv">
                <Link to={placeHref(id)} className="tg-sv__ph"><PlacePhoto id={id} /></Link>
                <button type="button" className="tg-pc__save is-on" onClick={() => toggleSaved(id)} aria-label={`Bỏ lưu ${p?.name ?? ''}`}><HeartFill size={18} /></button>
                <div className="tg-sv__b"><h3>{p?.name ?? 'Nơi không còn trong dữ liệu'}</h3><p className="tg-faint">{[p?.category, p?.area, p?.rating ? `★ ${p.rating.toFixed(1)}` : null].filter(Boolean).join(' · ')}</p>
                  {c ? <button type="button" className={`tg-btn tg-btn--sm ${c.chosen ? 'tg-btn--soft' : 'tg-btn--ghost'}`} disabled={busy || c.chosen} onClick={() => act({ type: 'select', place_id: id })}>{c.chosen ? <><Icon name="check" size={15} /> Trong chuyến</> : <><Icon name="plus" size={15} /> Thêm vào chuyến</>}</button>
                    : <span className="tg-faint tg-sv__note">{view ? 'Không nằm trong gợi ý của chuyến hiện tại' : 'Bắt đầu một chuyến để thêm'}</span>}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </Page>
  )
}

export function Account() {
  useTitle('Hồ sơ')
  const account = useAccount()
  const { trip } = useTrip()
  const { view } = useDecision()
  const prefs = trip.searchInput?.soft_weights.filter((w) => w.weight !== 0) ?? []
  const user = account?.kind === 'user' ? account : null
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Hồ sơ và dữ liệu</p><h1>Bạn và dữ liệu của bạn</h1><p>Không nguồn nào thì mọi thứ vẫn chạy. Mình chỉ nhớ gu khi bạn đồng ý.</p></div></header>
      <section className="tg-who"><span className="tg-who__av">{initialOf(account) ?? <Icon name="user" size={22} />}</span><div><b>{user ? user.name : 'Bạn đang dùng thử'}</b><span className="tg-muted">{user ? user.email ?? 'Tài khoản trên trình duyệt này' : 'Chuyến đi lưu trên máy chủ theo mã chuyến; danh sách chuyến lưu trên trình duyệt này.'}</span></div>{user ? <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => { signOut(); go('/login') }}>Đăng xuất</button> : <Link to="/login" className="tg-btn tg-btn--ghost tg-btn--sm">Tạo tài khoản</Link>}</section>
      <div className="tg-prof">
        <section className="tg-card tg-prof__c" aria-labelledby="tg-src-h"><h2 id="tg-src-h">Nguồn đã kết nối</h2><p className="tg-faint">Mỗi nguồn là tùy chọn; bạn tự thêm hoặc thu hồi.</p>
          {['TikTok', 'Google'].map((k) => <div key={k} className="tg-prof__row"><div><b>{k}</b><span className="tg-faint">Chưa kết nối</span></div><button type="button" className="tg-btn tg-btn--sm tg-btn--soft" disabled title="Sắp có">Sắp có</button></div>)}
        </section>
        <section className="tg-card tg-prof__c" aria-labelledby="tg-inf-h"><h2 id="tg-inf-h">Sở thích của chuyến hiện tại</h2><p className="tg-faint">Đây là điều bạn nói hoặc mình suy ra cho chuyến này, không phải cài đặt. Sửa ở vé chuyến.</p>
          {prefs.length === 0 ? <p className="tg-muted">Chưa có sở thích nào được ghi.</p> : prefs.map((w) => <div key={w.feature + w.value} className="tg-prof__row"><div><span className="tg-chip tg-chip--dash">{w.weight < 0 ? 'Tránh: ' : ''}{featureLabel(w.feature)}{w.value !== 'present' ? `: ${valueLabel(w.value)}` : ''}</span><span className="tg-faint"> {w.source === 'profile' ? 'từ hồ sơ' : 'từ lời bạn'}</span></div></div>)}
        </section>
      </div>
      {hasTrip(trip) && <section className="tg-card tg-prof__trip"><div><b>Chuyến đi đang lập</b><span className="tg-muted">{trip.searchInput?.context.days ? `${trip.searchInput.context.days} ngày · ` : ''}{view?.selected.length ?? trip.selected.length} nơi đã chọn</span></div><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => go(stepOf(trip).path)}>Mở tiếp</button></section>}
      <p className="tg-faint tg-prof__fine"><Icon name="shield" size={14} /> Hồ sơ dài hạn gắn với tài khoản (sắp có). Tín hiệu sức khỏe hay thể chất chỉ dùng trong phiên, không lưu lâu dài.</p>
    </Page>
  )
}

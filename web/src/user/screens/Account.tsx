import { useEffect, useState } from 'react'
import { featureLabel, valueLabel } from '../../data/labels'
import { deleteAccount, refreshAccount, setPatterns, signOut, updateProfile, uploadAvatar, useAccount, type Companions, type Me, type Mobility } from '../account'
import { calendarDisconnect } from '../today'
import { enablePush, KIND_LABEL, loadPrefs, pushSupported, savePrefs, type Prefs } from '../notify'
import { dateRange, info } from '../lib'
import { tripSummaries } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { TripSummary } from '../pd/types'
import { toast, toggleSaved, useUi } from '../store'
import { hasTrip, STEPS, stepOf, useTrip } from '../trip'
import { ArtCup, ArtHills, ArtRoute, Busy, Empty, go, Link, placeHref, PlacePhoto } from '../ui/common'
import { HeartFill, Icon } from '../ui/icons'
import { Page, useTitle } from '../ui/Shell'
import { useBegin } from './Discover'
import { GROUP_LABEL } from '../tu/labels'

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

// Journeys of the signed-in account; the server answers with one summary line each.
export function Trips() {
  useTitle('Chuyến của tôi')
  const { dispatch } = useTrip()
  const begin = useBegin()
  const [list, setList] = useState<TripSummary[] | null>(null)
  const [err, setErr] = useState(false)
  const [tab, setTab] = useState<Kind>('building')
  useEffect(() => {
    tripSummaries().then((l) => {
      setList(l)
      const first = (['confirmed', 'building', 'done'] as const).find((k) => l.some((t) => kindOf(t) === k)) // an upcoming trip first
      if (first) setTab(first)
    }, () => setErr(true))
  }, [])
  const open = (t: TripSummary, to?: string) => {
    dispatch({ type: 'reset' })
    dispatch({ type: 'set', patch: { journeyId: t.id, decisionId: t.stage === 'trip' ? null : t.id, planningId: t.stage === 'planning' ? t.id : null } })
    go(to ?? STEPS[STAGE_STEP[t.stage]].path)
  }
  const shown = (list ?? []).filter((t) => kindOf(t) === tab)
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Chuyến của tôi</p><h1>Chuyến đi của bạn</h1><p>Các chuyến của tài khoản này, mở được trên mọi máy.</p></div><button type="button" className="tg-btn tg-btn--primary" onClick={() => begin({ startWith: 'nothing', startText: null })}><Icon name="plus" size={18} /> Tạo chuyến đi</button></header>
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
                    <h2>Đà Lạt{t.days ? ` ${t.days} ngày${t.nights != null ? ` ${t.nights} đêm` : ''}` : ''}</h2>
                    <p className="tg-mono tg-muted">{[dateRange(t.start_date, t.days) ?? 'Chưa chốt ngày', t.people ? `${t.people} người` : null, `${t.places.length} nơi`].filter(Boolean).join(' · ')}</p>
                    {k === 'building' && <div className="tg-prog" aria-label={`Bước ${step + 1} trên ${STEPS.length}`}>{STEPS.map((s, i) => <span key={s.id} className={i < step ? 'is-done' : i === step ? 'is-now' : ''}><i />{s.label}</span>)}</div>}
                    <div className="tg-trip__act">
                      {k === 'building' && <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => open(t)}>Đi tiếp <Icon name="arrow" size={16} /></button>}
                      {k === 'confirmed' && <><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => go(`/today?journey=${t.id}`)}>Hôm nay</button><button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => open(t, '/plan')}>Xem lịch</button><button type="button" className="tg-link" onClick={() => open(t, '/plan')}>Sửa lại</button></>}
                      {k === 'done' && <><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => open(t, '/plan')}>Xem lại lịch</button><button type="button" className="tg-link" onClick={() => open(t, '/done')}>Phản hồi</button></>}
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
      <header className="tg-head"><div><p className="tg-kicker">Đã lưu</p><h1>Địa điểm bạn đã lưu</h1><p>Lưu theo tài khoản, mở được trên mọi máy. Nơi đã lưu không tự vào lịch; thêm vào chuyến khi nơi đó nằm trong gợi ý.</p></div></header>
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

const MOBILITY: [Mobility, string][] = [['motorbike', 'Xe máy'], ['car', 'Ô tô tự lái']]
const WHO: [Companions, string][] = [['solo', 'Đi một mình'], ['partner', 'Với người yêu / vợ chồng'], ['friends', 'Với bạn bè'], ['kids', 'Với con nhỏ'], ['parents', 'Với bố mẹ']]

export function Account() {
  useTitle('Hồ sơ')
  const account = useAccount()
  const { trip } = useTrip()
  const prefs = trip.searchInput?.soft_weights.filter((w) => w.weight !== 0) ?? []
  const groups = trip.searchInput?.liked_groups ?? []
  if (!account) return null
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Hồ sơ và dữ liệu</p><h1>Bạn và dữ liệu của bạn</h1><p>Mọi trường đều tùy chọn. Hồ sơ chỉ là gợi ý ban đầu; điều bạn nói cho chuyến này luôn thắng.</p></div></header>
      <section className="tg-who">
        <AvatarPicker account={account} />
        <div><b>{account.name || 'Bạn'}</b><span className="tg-muted">{account.email}</span></div>
        <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => { void signOut(); go('/login') }}>Đăng xuất</button>
      </section>
      <div className="tg-prof">
        <ProfileForm account={account} />
        <section className="tg-card tg-prof__c" aria-labelledby="tg-inf-h"><h2 id="tg-inf-h">Sở thích của chuyến hiện tại</h2><p className="tg-faint">Đây là điều bạn nói hoặc mình suy ra cho chuyến này, không phải cài đặt. Sửa ở vé chuyến.</p>
          {groups.length > 0 && <div className="tg-prof__row"><div><span className="tg-chip tg-chip--dash">Muốn đi: {groups.map((g) => GROUP_LABEL[g] ?? g).join(', ')}</span><span className="tg-faint"> từ lời bạn</span></div></div>}
          {prefs.length === 0 && groups.length === 0 ? <p className="tg-muted">Chưa có sở thích nào được ghi.</p> : prefs.map((w) => <div key={w.feature + w.value} className="tg-prof__row"><div><span className="tg-chip tg-chip--dash">{w.weight < 0 ? 'Tránh: ' : ''}{featureLabel(w.feature)}{w.value !== 'present' ? `: ${valueLabel(w.value)}` : ''}</span><span className="tg-faint"> {w.source === 'profile' ? 'từ hồ sơ' : 'từ lời bạn'}</span></div></div>)}
        </section>
      </div>
      {hasTrip(trip) && <CurrentTrip />}
      <RememberChoices account={account} />
      <NotifyPrefs />
      {account.calendar && <CalendarLink />}
      <DeleteAccount />
      <p className="tg-faint tg-prof__fine"><Icon name="shield" size={14} /> Tín hiệu sức khỏe hay thể chất chỉ dùng trong phiên, không lưu lâu dài. Không thu vị trí GPS.</p>
    </Page>
  )
}

// The trip in this browser, told the same way as in Chuyến của tôi (the server summary decides Đang lập / Sắp tới / Đã đi).
function CurrentTrip() {
  const { trip } = useTrip()
  const { view } = useDecision()
  const [t, setT] = useState<TripSummary | null | undefined>()
  useEffect(() => { tripSummaries().then((l) => setT(l.find((x) => x.id === trip.journeyId) ?? null), () => setT(null)) }, [trip.journeyId])
  if (t === undefined) return null
  const k = t ? kindOf(t) : 'building'
  const days = t?.days ?? trip.searchInput?.context.days
  const places = t ? t.places.length : view?.selected.length ?? trip.selected.length
  const title = k === 'building' ? 'Chuyến đi đang lập' : k === 'confirmed' ? 'Chuyến sắp tới · đã chốt lịch' : 'Chuyến đã đi'
  const line = [days ? `${days} ngày` : null, t ? dateRange(t.start_date, t.days) : null, `${places} nơi ${k === 'building' ? 'đã chọn' : 'trong lịch'}`].filter(Boolean).join(' · ')
  return (
    <section className="tg-card tg-prof__trip"><div><b>{title}</b><span className="tg-muted">{line}</span></div>
      {k === 'building' ? <button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => go(stepOf(trip).path)}>Mở tiếp</button>
        : k === 'confirmed' ? <button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => go(`/today?journey=${t!.id}`)}>Mở Hôm nay</button>
        : <button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={() => go('/trips')}>Chuyến của tôi</button>}
    </section>
  )
}

function AvatarPicker({ account }: { account: Me }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const pick = (file: File | undefined) => {
    if (!file) return
    if (file.size > 5 * 1024 * 1024) return setErr('Ảnh tối đa 5 MB.')
    setBusy(true); setErr(null)
    uploadAvatar(file).then(() => toast('Đã đổi ảnh đại diện'), () => setErr('Ảnh này chưa dùng được. Thử ảnh JPG, PNG hoặc WebP khác.')).finally(() => setBusy(false))
  }
  return (
    <div className="tg-avpick">
      <label className="tg-who__av tg-avpick__btn" title="Đổi ảnh đại diện" aria-busy={busy}>
        {account.avatar ? <img src={account.avatar} alt="" referrerPolicy="no-referrer" /> : <span>{(account.name || account.email || '?')[0].toUpperCase()}</span>}
        <input type="file" accept="image/jpeg,image/png,image/webp" className="tg-sr" aria-label="Đổi ảnh đại diện" disabled={busy} onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
        <i aria-hidden="true"><Icon name="plus" size={14} /></i>
      </label>
      {err && <small className="tg-auth__err" role="alert">{err}</small>}
    </div>
  )
}

function ProfileForm({ account }: { account: Me }) {
  const [name, setName] = useState(account.name)
  const [city, setCity] = useState(account.home_city ?? '')
  const [mobility, setMobility] = useState<string>(account.usual_mobility ?? '')
  const [who, setWho] = useState<string>(account.usual_companions ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = name !== account.name || city !== (account.home_city ?? '') || mobility !== (account.usual_mobility ?? '') || who !== (account.usual_companions ?? '')
  const save = () => {
    setBusy(true); setErr(null)
    updateProfile({ display_name: name, home_city: city, usual_mobility: (mobility || null) as Mobility | null, usual_companions: (who || null) as Companions | null })
      .then(() => toast('Đã lưu hồ sơ'), (e: Error) => setErr(e.message.includes('too long') ? 'Có trường dài quá, rút gọn lại nhé.' : 'Chưa lưu được, thử lại nhé.'))
      .finally(() => setBusy(false))
  }
  return (
    <section className="tg-card tg-prof__c" aria-labelledby="tg-me-h">
      <h2 id="tg-me-h">Hồ sơ</h2><p className="tg-faint">Dùng làm gợi ý ban đầu cho chuyến mới, hiện với nhãn “từ hồ sơ”.</p>
      <form className="tg-pform" onSubmit={(e) => { e.preventDefault(); save() }}>
        <label className="tg-auth__f"><span>Tên hiển thị</span><input className="tg-input" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} autoComplete="nickname" /></label>
        <label className="tg-auth__f"><span>Thành phố bạn hay xuất phát</span><input className="tg-input" value={city} maxLength={80} onChange={(e) => setCity(e.target.value)} placeholder="Ví dụ: Hồ Chí Minh" autoComplete="address-level2" /></label>
        <label className="tg-auth__f"><span>Phương tiện hay dùng ở Đà Lạt</span><select className="tg-input" value={mobility} onChange={(e) => setMobility(e.target.value)}><option value="">Chưa chọn</option>{MOBILITY.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="tg-auth__f"><span>Hay đi với ai</span><select className="tg-input" value={who} onChange={(e) => setWho(e.target.value)}><option value="">Chưa chọn</option>{WHO.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        {err && <small className="tg-auth__err" role="alert">{err}</small>}
        <button type="submit" className="tg-btn tg-btn--primary tg-btn--sm" disabled={!dirty || busy}>{busy ? 'Đang lưu…' : 'Lưu hồ sơ'}</button>
      </form>
    </section>
  )
}

// Off by default for anyone who did not tick it: nothing is remembered, and turning it off forgets what was learned.
function RememberChoices({ account }: { account: Me }) {
  const on = account.consents.patterns === true
  const [busy, setBusy] = useState(false)
  const change = (next: boolean) => {
    setBusy(true)
    setPatterns(next).then(() => toast(next ? 'Đã bật nhớ lựa chọn' : 'Đã tắt và xóa phần đã nhớ'), () => toast('Chưa lưu được, thử lại nhé')).finally(() => setBusy(false))
  }
  return (
    <div className="tg-prof">
      <section className="tg-card tg-prof__c" aria-labelledby="tg-rc-h">
        <h2 id="tg-rc-h">Nhớ lựa chọn của bạn</h2>
        <p className="tg-faint">Khi bạn chọn giống nhau qua vài chuyến (cách tới Đà Lạt, phương tiện, ngân sách, giờ nhận phòng, gu đi chơi), các chuyến sau không hỏi lại mà dùng làm gợi ý, hiện trên vé chuyến và sửa được. Điều bạn nói cho chuyến hiện tại luôn thắng.</p>
        <div className="tg-npref"><label><input type="checkbox" checked={on} disabled={busy} onChange={(e) => change(e.target.checked)} /> Nhớ lựa chọn của tôi qua các chuyến</label></div>
      </section>
    </div>
  )
}

function NotifyPrefs() {
  const [p, setP] = useState<Prefs | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { loadPrefs().then(setP, () => {}) }, [])
  if (!p) return null
  // Optimistic: the box changes at once; a failed save puts it back.
  const save = (patch: Parameters<typeof savePrefs>[0]) => {
    const before = p
    setP({ ...p, ...patch })
    setBusy(true)
    savePrefs(patch).then(setP, () => { setP(before); toast('Chưa lưu được, thử lại nhé') }).finally(() => setBusy(false))
  }
  const toggle = (k: string) => save({ enabled_kinds: p.enabled_kinds.includes(k) ? p.enabled_kinds.filter((x) => x !== k) : [...p.enabled_kinds, k] })
  return (
    <div className="tg-prof">
      <section className="tg-card tg-prof__c" aria-labelledby="tg-np-h">
        <h2 id="tg-np-h">Thông báo</h2>
        <p className="tg-faint">{p.push_devices ? `Đang nhận trên ${p.push_devices} trình duyệt.` : 'Chưa bật trên trình duyệt nào; vẫn có trong Hộp thông báo.'} Không nhắn từ {p.quiet_start} đến {p.quiet_end}.</p>
        <div className="tg-npref">
          <label><input type="checkbox" checked={p.paused} disabled={busy} onChange={(e) => save({ paused: e.target.checked })} /> Tạm im mọi thông báo</label>
          {p.kinds.map((k) => <label key={k}><input type="checkbox" checked={p.enabled_kinds.includes(k)} disabled={busy || p.paused} onChange={() => toggle(k)} /> {KIND_LABEL[k] ?? k}</label>)}
        </div>
        {pushSupported() && Notification.permission === 'default' && <button type="button" className="tg-btn tg-btn--soft tg-btn--sm" onClick={async () => { const r = await enablePush(); if (r === 'granted') { toast('Đã bật thông báo'); loadPrefs().then(setP) } }}>Bật trên trình duyệt này</button>}
      </section>
    </div>
  )
}

function CalendarLink() {
  const [step, setStep] = useState<0 | 1>(0)
  const [drop, setDrop] = useState(false)
  const [busy, setBusy] = useState(false)
  const off = () => {
    setBusy(true)
    calendarDisconnect(drop).then(() => { toast('Đã ngắt Google Calendar'); return refreshAccount() }, () => toast('Chưa ngắt được, thử lại nhé')).finally(() => setBusy(false))
  }
  return (
    <section className="tg-card tg-del" aria-labelledby="tg-gcal-h">
      <div><h2 id="tg-gcal-h">Google Calendar</h2><p className="tg-faint">Đã kết nối. TripGuardian chỉ ghi vào lịch riêng do nó tạo, và chỉ khi bạn xác nhận.</p></div>
      {step === 0 ? <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => setStep(1)}>Ngắt kết nối…</button> : (
        <div className="tg-del__confirm">
          <label className="tg-auth__check"><input type="checkbox" checked={drop} onChange={(e) => setDrop(e.target.checked)} /> <span>Xóa luôn các lịch TripGuardian trong Google Calendar</span></label>
          <div><button type="button" className="tg-btn tg-btn--sm tg-del__yes" disabled={busy} onClick={off}>Ngắt kết nối</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => setStep(0)}>Thôi</button></div>
        </div>
      )}
    </section>
  )
}

function DeleteAccount() {
  const [step, setStep] = useState<0 | 1>(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const remove = () => {
    setBusy(true)
    deleteAccount().then(() => go('/login'), () => { setErr(true); setBusy(false) })
  }
  return (
    <section className="tg-card tg-del" aria-labelledby="tg-del-h">
      <div><h2 id="tg-del-h">Xóa tài khoản</h2><p className="tg-faint">Xóa hồ sơ, ảnh, liên kết Google Calendar và thông báo. Chuyến đi và số liệu sử dụng vẫn giữ để thống kê nhưng không còn gắn với bạn.</p></div>
      {step === 0 ? <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm tg-del__go" onClick={() => setStep(1)}>Xóa tài khoản…</button> : (
        <div className="tg-del__confirm" role="alertdialog" aria-labelledby="tg-del-q">
          <p id="tg-del-q"><b>Xóa vĩnh viễn?</b> Không khôi phục được.</p>
          {err && <small className="tg-auth__err" role="alert">Chưa xóa được, thử lại nhé.</small>}
          <div><button type="button" className="tg-btn tg-btn--sm tg-del__yes" disabled={busy} onClick={remove}>{busy ? 'Đang xóa…' : 'Xóa vĩnh viễn'}</button><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" disabled={busy} onClick={() => setStep(0)}>Giữ tài khoản</button></div>
        </div>
      )}
    </section>
  )
}

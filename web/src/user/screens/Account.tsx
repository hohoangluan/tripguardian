import { useEffect, useState } from 'react'
import { deleteAccount, refreshAccount, signOut, updateProfile, uploadAvatar, useAccount, type Companions, type Me, type Mobility } from '../account'
import { calendarDisconnect } from '../today'
import { track } from '../events'
import { enablePush, KIND_LABEL, loadPrefs, pushSupported, savePrefs, type Prefs } from '../notify'
import { useWarm } from '../../data/store'
import { dateRange, info } from '../lib'
import { deleteTrip, tripSummaries } from '../pd/api'
import { useDecision } from '../pd/decision'
import { useFriends } from '../social'
import type { TripSummary } from '../pd/types'
import { toast, toggleSaved, toggleTheme, useUi } from '../store'
import { STEPS, useTrip } from '../trip'
import { ArtCup, ArtHills, ArtRoute, Busy, Empty, go, Link, placeHref, PlacePhoto } from '../ui/common'
import { HeartFill, Icon, type IconName } from '../ui/icons'
import { Page, useTitle } from '../ui/Shell'
import { openShare, openTheme, useBegin } from '../home/dialogs'
import { themeOf } from '../home/themes'
import { GuestNotice } from './Guest'

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
  const { trip, dispatch } = useTrip()
  const begin = useBegin()
  const [list, setList] = useState<TripSummary[] | null>(null)
  const [err, setErr] = useState(false)
  const [tab, setTab] = useState<Kind>('building')
  const account = useAccount()
  const member = !!account && !account.guest
  useEffect(() => {
    tripSummaries().then((l) => {
      setList(l)
      const first = (['building', 'confirmed', 'done'] as const).find((k) => l.some((t) => kindOf(t) === k))
      if (first) setTab(first)
    }, () => setErr(true))
  }, [])
  const open = (t: TripSummary, to?: string) => {
    dispatch({ type: 'reset' })
    dispatch({ type: 'set', patch: { journeyId: t.id, decisionId: t.stage === 'trip' ? null : t.id, planningId: t.stage === 'planning' ? t.id : null } })
    go(to ?? STEPS[STAGE_STEP[t.stage]].path)
  }
  const [asking, setAsking] = useState<string | null>(null) // the trip waiting for the user's yes to be removed
  const [removing, setRemoving] = useState(false)
  const remove = (t: TripSummary) => {
    setRemoving(true)
    deleteTrip(t.id).then(() => {
      setList((l) => l && l.filter((x) => x.id !== t.id))
      try { localStorage.removeItem(`tg.journey.pending.${t.id}`) } catch { /* nothing stored */ }
      if (trip.journeyId === t.id) dispatch({ type: 'reset' })
      setAsking(null)
      toast('Đã xóa chuyến')
    }, () => toast('Chưa xóa được, bạn thử lại nhé')).finally(() => setRemoving(false))
  }
  const shown = (list ?? []).filter((t) => kindOf(t) === tab)
  return (
    <Page>
      <GuestNotice />
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
                    <h2>Đà Lạt{t.days ? ` ${t.days} ngày` : ''}</h2>
                    <p className="tg-mono tg-muted">{[dateRange(t.start_date, t.days) ?? 'Chưa chốt ngày', t.people ? `${t.people} người` : null, `${t.places.length} nơi`].filter(Boolean).join(' · ')}</p>
                    {k === 'building' && <div className="tg-prog" aria-label={`Bước ${step + 1} trên ${STEPS.length}`}>{STEPS.map((s, i) => <span key={s.id} className={i < step ? 'is-done' : i === step ? 'is-now' : ''}><i />{s.label}</span>)}</div>}
                    <div className="tg-trip__act">
                      {k === 'building' && <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => open(t)}>Đi tiếp <Icon name="arrow" size={16} /></button>}
                      {k === 'confirmed' && <><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => open(t, '/plan')}>Xem lịch</button><button type="button" className="tg-link" onClick={() => open(t, '/plan')}>Sửa lại</button></>}
                      {k === 'done' && <><button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => open(t, '/plan')}>Xem lại lịch</button><button type="button" className="tg-link" onClick={() => open(t, '/done')}>Phản hồi</button></>}
                      {member && t.stage !== 'trip' && <button type="button" className="tg-link" onClick={() => openShare(t)}><Icon name="send" size={14} /> Gửi cho bạn bè</button>}
                      {asking === t.id ? (
                        <span className="tg-trip__ask" role="alertdialog" aria-label="Xóa chuyến này?">Xóa chuyến này?<button type="button" className="tg-btn tg-btn--sm tg-del__yes" disabled={removing} onClick={() => remove(t)}>{removing ? 'Đang xóa…' : 'Xóa'}</button><button type="button" className="tg-link" disabled={removing} onClick={() => setAsking(null)}>Giữ lại</button></span>
                      ) : <button type="button" className="tg-trip__del" aria-label="Xóa chuyến này" title="Xóa chuyến này" onClick={() => setAsking(t.id)}><Icon name="trash" size={15} /></button>}
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
  const themes = useUi((u) => u.savedThemes).map(themeOf).filter((t) => t !== undefined)
  const { view, act, busy } = useDecision()
  const [f, setF] = useState('all')
  useWarm(saved)
  const cards = new Map(view?.groups.flatMap((g) => g.cards).map((c) => [c.id, c]) ?? [])
  const items = saved.filter((id) => f === 'all' || info(id)?.group === f)
  const count = (k: string) => saved.filter((id) => k === 'all' || info(id)?.group === k).length
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Đã lưu</p><h1>Địa điểm bạn đã lưu</h1><p>Lưu theo tài khoản, mở được trên mọi máy. Nơi đã lưu không tự vào lịch; thêm vào chuyến khi nơi đó nằm trong gợi ý.</p></div></header>
      {themes.length > 0 && (
        <section className="tg-sv-themes" aria-label="Chủ đề đã lưu">
          {themes.map((t) => (
            <article key={t.id} className="tg-sv-theme">
              <button type="button" onClick={() => openTheme(t.id)}><img src={t.photo} alt="" /><span><b>{t.short}</b><small>{t.category}</small></span></button>
              <button type="button" className="tg-pc__save is-on" onClick={() => toggleTheme(t.id, t.short)} aria-label={`Bỏ lưu ${t.short}`}><HeartFill size={16} /></button>
            </article>
          ))}
        </section>
      )}
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

const MOBILITY: [Mobility, string, IconName][] = [['motorbike', 'Xe máy', 'route'], ['car', 'Ô tô', 'map'], ['walk', 'Không dùng xe riêng', 'pin']]
const WHO: [Companions, string][] = [['solo', 'Đi một mình'], ['partner', 'Với người yêu'], ['friends', 'Với bạn bè'], ['kids', 'Với con nhỏ'], ['parents', 'Với bố mẹ']]
const FORM_ERR = (e: Error) => e.message.includes('too long') ? 'Có trường dài quá, rút gọn lại nhé.' : e.message === 'nickname is taken' ? 'Nickname này đã có người dùng.' : e.message.startsWith('nickname') ? 'Nickname 3–24 ký tự: chữ thường không dấu, số, dấu chấm, gạch dưới.' : 'Chưa lưu được, thử lại nhé.'

export function Account() {
  useTitle('Hồ sơ')
  const account = useAccount()
  const friends = useFriends(!!account && !account.guest)
  const savedN = useUi((u) => u.saved.length + u.savedThemes.length)
  const [trips, setTrips] = useState<TripSummary[] | null>(null)
  // The numbers are the server's, read again every half minute and when the tab comes back; a failed read keeps the
  // last numbers (or shows a dash), never a made-up zero.
  useEffect(() => {
    const pull = () => { if (document.visibilityState === 'visible') tripSummaries().then(setTrips, () => {}) }
    pull()
    const t = setInterval(pull, 30_000)
    document.addEventListener('visibilitychange', pull)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', pull) }
  }, [])
  if (!account) return null
  const done = trips?.filter((t) => t.confirmed).length ?? 0
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Hồ sơ</p><h1>Hồ sơ của bạn</h1><p>Bạn bè thấy tên, nickname, giới thiệu và ảnh. Gu đi chơi chỉ là gợi ý ban đầu cho chuyến mới; điều bạn nói trong chuyến luôn thắng.</p></div></header>
      <section className="tg-card tg-me" aria-label="Tài khoản">
        <AvatarPicker account={account} />
        <div className="tg-me__id"><b>{account.name || 'Bạn'}</b>{account.nickname && <span className="tg-muted">@{account.nickname}</span>}<span className="tg-faint">{account.email}</span></div>
        <dl className="tg-me__stats">
          <div><dt>Chuyến</dt><dd><Link to="/trips">{trips ? trips.length : '–'}</Link></dd></div>
          <div><dt>Đã chốt lịch</dt><dd>{trips ? done : '–'}</dd></div>
          <div><dt>Đã lưu</dt><dd><Link to="/saved">{savedN}</Link></dd></div>
          <div><dt>Bạn bè</dt><dd>{friends ? friends.friends.length : '–'}</dd></div>
        </dl>
        <button type="button" className="tg-btn tg-btn--ghost tg-btn--sm" onClick={() => { void signOut(); go('/login') }}>Đăng xuất</button>
      </section>
      <div className="tg-prof">
        <ProfileForm account={account} />
        <TasteCard account={account} />
      </div>
      <NotifyPrefs />
      {account.calendar && <CalendarLink />}
      <DeleteAccount />
      <p className="tg-faint tg-prof__fine"><Icon name="shield" size={14} /> Tín hiệu sức khỏe hay thể chất chỉ dùng trong phiên, không lưu lâu dài. Không thu vị trí GPS.</p>
    </Page>
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

// What friends see: name, nickname, a line about you. One small form.
function ProfileForm({ account }: { account: Me }) {
  const [name, setName] = useState(account.name)
  const [nick, setNick] = useState(account.nickname ?? '')
  const [bio, setBio] = useState(account.bio)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = name !== account.name || nick !== (account.nickname ?? '') || bio !== account.bio
  const save = () => {
    setBusy(true); setErr(null)
    updateProfile({ display_name: name, nickname: nick || null, bio }).then(() => toast('Đã lưu hồ sơ'), (e: Error) => setErr(FORM_ERR(e))).finally(() => setBusy(false))
  }
  return (
    <section className="tg-card tg-prof__c" aria-labelledby="tg-me-h">
      <h2 id="tg-me-h">Bạn bè nhìn thấy</h2>
      <form className="tg-pform" onSubmit={(e) => { e.preventDefault(); save() }}>
        <label className="tg-auth__f"><span>Tên hiển thị</span><input className="tg-input" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
        <label className="tg-auth__f"><span>Nickname</span><input className="tg-input" value={nick} maxLength={24} onChange={(e) => setNick(e.target.value.toLowerCase())} placeholder="ví dụ: an.nguyen" autoComplete="nickname" /><small className="tg-faint">Bạn bè tìm và kết bạn bằng nickname.</small></label>
        <label className="tg-auth__f"><span>Giới thiệu ngắn</span><input className="tg-input" value={bio} maxLength={160} onChange={(e) => setBio(e.target.value)} placeholder="Ví dụ: Mê cà phê và săn mây" /></label>
        {err && <small className="tg-auth__err" role="alert">{err}</small>}
        <button type="submit" className="tg-btn tg-btn--primary tg-btn--sm" disabled={!dirty || busy}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
      </form>
    </section>
  )
}

// Where the user usually starts, how they get around, who they go with: a prior for a new trip (shown as "từ hồ sơ"
// and replaced by anything said in the trip). A tap saves; tapping the chosen one again clears it.
function TasteCard({ account }: { account: Me }) {
  const [city, setCity] = useState(account.home_city ?? '')
  const [busy, setBusy] = useState(false)
  const save = (patch: Parameters<typeof updateProfile>[0], done?: string) => {
    setBusy(true)
    updateProfile(patch).then(() => { if (done) toast(done) }, (e: Error) => toast(FORM_ERR(e))).finally(() => setBusy(false))
  }
  return (
    <section className="tg-card tg-prof__c" aria-labelledby="tg-taste-h">
      <h2 id="tg-taste-h">Gu đi chơi của bạn</h2>
      <p className="tg-faint">Mình dùng để hỏi ít hơn khi bạn lên chuyến mới. Bạn vẫn đổi được ngay trong từng chuyến.</p>
      <div className="tg-taste">
        <form className="tg-taste__row" onSubmit={(e) => { e.preventDefault(); save({ home_city: city }, 'Đã lưu nơi xuất phát') }}>
          <label htmlFor="tg-city">Bạn hay xuất phát từ đâu?</label>
          <div className="tg-taste__line"><input id="tg-city" className="tg-input" value={city} maxLength={80} onChange={(e) => setCity(e.target.value)} placeholder="Ví dụ: Hồ Chí Minh" autoComplete="address-level2" /><button type="submit" className="tg-btn tg-btn--soft tg-btn--sm" disabled={busy || city === (account.home_city ?? '')}>Lưu</button></div>
        </form>
        <div className="tg-taste__row" role="group" aria-labelledby="tg-mob">
          <span id="tg-mob">Ở Đà Lạt bạn hay đi bằng</span>
          <div className="tg-basics__chips">{MOBILITY.map(([v, l, ic]) => <button key={v} type="button" className="tg-chip" aria-pressed={account.usual_mobility === v} disabled={busy} onClick={() => save({ usual_mobility: account.usual_mobility === v ? null : v })}><Icon name={ic} size={14} /> {l}</button>)}</div>
        </div>
        <div className="tg-taste__row" role="group" aria-labelledby="tg-who">
          <span id="tg-who">Bạn hay đi với ai</span>
          <div className="tg-basics__chips">{WHO.map(([v, l]) => <button key={v} type="button" className="tg-chip" aria-pressed={account.usual_companions === v} disabled={busy} onClick={() => save({ usual_companions: account.usual_companions === v ? null : v })}>{l}</button>)}</div>
        </div>
      </div>
    </section>
  )
}

function NotifyPrefs() {
  const [p, setP] = useState<Prefs | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { loadPrefs().then(setP, () => {}); track('install_prompt_seen') }, [])
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
    <div className="tg-prof is-one">
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

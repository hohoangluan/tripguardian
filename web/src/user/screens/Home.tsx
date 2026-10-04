import { coversOf, placeById } from '../../data/store'
import { navigate } from '../../router'
import { Icon, Page, PlaceCover } from '../../ui/bits'
import { LineArt } from '../../ui/LineArt'
import { useAccount } from '../account'
import { useDecision } from '../pd/decision'
import { STEPS, stepOf, useTrip, initialTrip } from '../trip'
import { EXPLORE } from './Explore'

// UI spec §4 Trang 0: only for someone who already has a trip. Four blocks, fixed, no feed:
// every card leads to one decision, never to something to read.
export function Home() {
  const account = useAccount()
  const { trip, dispatch } = useTrip()
  const { view } = useDecision()
  const step = stepOf(trip)
  const name = account?.kind === 'user' ? account.name.split(' ').pop() : null
  const conflicts = view?.feasibility.conflicts.length ?? 0
  const todo = STEPS.length - step.index + conflicts
  const picked = view?.selected ?? trip.selected
  const coverId = picked.find((id) => coversOf(id).length)
  const saved = view?.wishlist ?? []
  const days = trip.searchInput?.context.days ?? trip.days
  const start = trip.searchInput?.context.start_date ?? null
  const dates = start ? `${new Date(start + 'T00:00').toLocaleDateString('vi-VN', { day: 'numeric', month: 'numeric' })} · ` : ''

  const fresh = () => {
    if (!confirm('Bắt đầu chuyến mới? Chuyến đang lập sẽ được thay thế.')) return
    dispatch({ type: 'set', patch: { ...initialTrip } })
    navigate('/app/start')
  }

  return (
    <Page>
      <header className="uhead home-head">
        <h1>Chào {name ?? 'bạn'},</h1>
        <p>{todo > 0 ? `Chuyến Đà Lạt của bạn còn ${todo} việc chưa xong.` : 'Chuyến Đà Lạt của bạn đã xong cả bốn bước.'}</p>
      </header>

      <section className="home-trip ucard">
        <div className="home-trip__img">{coverId ? <PlaceCover id={coverId} /> : <LineArt variant="spot" seed={3} />}</div>
        <div className="home-trip__body">
          <span className="uhead__kicker">Chuyến đang lập</span>
          <h2>Đà Lạt {days} ngày</h2>
          <p className="mono">
            {dates}
            {days} ngày · {picked.length} nơi đã chọn
          </p>
          <ol className="home-steps" aria-label="Tiến trình">
            {STEPS.map((s, i) => (
              <li key={s.path} className={i < step.index ? 'is-done' : i === step.index ? 'is-now' : ''}>
                <i />
                <span>{s.label}</span>
              </li>
            ))}
          </ol>
          <div className="home-trip__foot">
            {conflicts > 0 ? (
              <p className="home-warn">
                <Icon name="alert" size={17} /> Còn {conflicts} xung đột chưa xử lý
              </p>
            ) : (
              <span />
            )}
            <button className="btn" onClick={() => navigate(conflicts ? '/app/feasibility' : step.path)}>
              Đi tiếp
            </button>
          </div>
        </div>
      </section>

      <div className="home-two">
        <section className="ucard">
          <h2 className="utitle">
            Nơi đã lưu <small>{saved.length}</small>
          </h2>
          {saved.length ? (
            <ul className="home-list">
              {saved.slice(0, 3).map((w) => (
                <li key={w.id}>
                  <button onClick={() => navigate(`/app/place/${encodeURIComponent(w.id)}`)}>
                    <span className="home-list__img">
                      <PlaceCover id={w.id} fallback={<LineArt variant="spot" seed={w.name.length} />} />
                    </span>
                    <span>
                      <b>{placeById(w.id)?.name ?? w.name}</b>
                      <small>{w.reason}</small>
                    </span>
                    <Icon name="next" size={16} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nơi bạn để dành cho dịp khác sẽ nằm ở đây.</p>
          )}
        </section>
        <section className="ucard">
          <h2 className="utitle">
            Chuyến đã đi <small>0</small>
          </h2>
          <p className="hint">Đi xong chuyến này, nó sẽ nằm ở đây, kèm lối tắt “Dùng lại gu chuyến này”.</p>
        </section>
      </div>

      <section className="home-explore">
        <h2 className="utitle">Khám phá Đà Lạt</h2>
        <div className="explore-cards">
          {EXPLORE.map((e) => (
            <article key={e.title} className="explore-card">
              <div className="explore-card__art">
                <Icon name={e.icon} size={56} />
              </div>
              <p>
                <b>{e.title}</b> · {e.note}
              </p>
              <span className="soon">sắp mở</span>
            </article>
          ))}
        </div>
      </section>

      <div className="home-new">
        <LineArt variant="spot" seed={11} />
        <span>Bắt đầu một chuyến mới</span>
        <button className="btn btn--ghost btn--small" onClick={fresh}>
          Chuyến mới
        </button>
      </div>
    </Page>
  )
}

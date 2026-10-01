import gsap from 'gsap'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { featureLabel, prefLabel } from '../../data/labels'
import { placeById, VEHICLE_LABEL } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Chip, Icon, Page } from '../../ui/bits'
import { fold } from '../search'
import { useTrip, WHO_LABEL, type Pref, type TripState } from '../trip'

interface Option {
  label: string
  prefs?: Record<string, Pref['weight']>
  patch?: Partial<TripState>
}

interface Question {
  key: string
  ask: (t: TripState) => string
  multi?: boolean
  options: Option[]
  when?: (t: TripState) => boolean
}

// Only questions that change the shortlist or the schedule (Project_Context §12).
const QUESTIONS: Question[] = [
  {
    key: 'vibe',
    multi: true,
    ask: (t) => (t.experience === 'returning' ? 'Lần này bạn muốn thử gì khác?' : 'Chuyến này bạn muốn thấy gì nhất? Chọn bao nhiêu cũng được.'),
    options: [
      { label: 'View đồi núi', prefs: { scenic_view: 'love' } },
      { label: 'Săn mây', prefs: { cloud_hunting: 'love' } },
      { label: 'Thiên nhiên, thác, rừng', prefs: { nature: 'love' } },
      { label: 'Vườn hoa', prefs: { flower_garden: 'love' } },
      { label: 'Chụp ảnh đẹp', prefs: { photo_spot: 'love' } },
      { label: 'Cà phê xinh, ngồi lâu', prefs: { cozy_decor: 'love', long_stay_chill: 'love' } },
      { label: 'Hái dâu, vườn trái cây', prefs: { pick_your_own: 'love' } },
      { label: 'Có thú để chơi', prefs: { animals: 'love' } },
      { label: 'Leo núi, trekking', prefs: { hiking: 'love' } },
      { label: 'Kiến trúc, di tích', prefs: { heritage_architecture: 'love' } },
    ],
  },
  {
    key: 'mood',
    ask: () => 'Bạn thích chỗ đông vui hay yên tĩnh?',
    options: [
      { label: 'Yên tĩnh', prefs: { noise: 'love', crowd: 'love' } },
      { label: 'Đông vui, có nhạc', prefs: { live_music: 'love' } },
      { label: 'Sao cũng được' },
    ],
  },
  {
    key: 'pace',
    ask: (t) => `Mỗi ngày ${t.experience === 'first' ? '(lần đầu thường 3–4 nơi là vừa) ' : ''}bạn muốn đi thế nào?`,
    options: [
      { label: 'Thong thả, ít nơi', patch: { pace: 'slow' } },
      { label: 'Vừa phải', patch: { pace: 'normal' } },
      { label: 'Đi được càng nhiều càng tốt', patch: { pace: 'packed' } },
    ],
  },
  {
    key: 'effort',
    ask: (t) => (t.who.includes('parents') || t.who.includes('kids') ? 'Đi cùng bố mẹ hoặc trẻ nhỏ: nên hạn chế leo dốc và đi bộ xa không?' : 'Leo dốc, đi bộ xa có ổn với bạn không?'),
    options: [
      { label: 'Hạn chế giúp mình', prefs: { steep_or_stairs: 'avoid', long_walk: 'avoid' } },
      { label: 'Ổn cả' },
    ],
  },
  {
    key: 'food',
    multi: true,
    ask: () => 'Còn chuyện ăn uống, bạn để ý điều gì?',
    options: [
      { label: 'Món đặc sản', prefs: { local_specialty_food: 'love' } },
      { label: 'Có món chay', prefs: { vegetarian_options: 'love' } },
      { label: 'Đáng tiền', prefs: { value_for_money: 'love' } },
      { label: 'Không phải chờ lâu', prefs: { wait_time: 'love' } },
    ],
  },
]

// Free text -> features, shown back to the user before anything is applied.
const KEYWORDS: [RegExp, string][] = [
  [/may|san may/, 'cloud_hunting'],
  [/hoa/, 'flower_garden'],
  [/chup|song ao|check in/, 'photo_spot'],
  [/yen|vang|it nguoi/, 'noise'],
  [/dau|hai trai/, 'pick_your_own'],
  [/chay/, 'vegetarian_options'],
  [/cafe|ca phe|decor/, 'cozy_decor'],
  [/thac|rung|thien nhien|suoi/, 'nature'],
  [/view|ngam canh|doi/, 'scenic_view'],
  [/leo nui|trek/, 'hiking'],
  [/hoang hon|binh minh/, 'sunset_view'],
  [/dac san/, 'local_specialty_food'],
  [/nhac/, 'live_music'],
  [/cam trai|glamping/, 'camping'],
]

export function Discover() {
  const { trip, dispatch } = useTrip()
  const queue = useMemo(() => QUESTIONS.filter((q) => !q.when || q.when(trip)), [trip])
  const [turn, setTurn] = useState(() => queue.findIndex((q) => !trip.answered.includes(q.key)))
  const [log, setLog] = useState<{ q: string; a: string }[]>([])
  const [picked, setPicked] = useState<number[]>([])
  const [text, setText] = useState('')
  const [guess, setGuess] = useState<string[]>([])
  const done = turn < 0 || turn >= queue.length
  const q = done ? null : queue[turn]
  const thread = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const el = thread.current?.lastElementChild
    if (!el || story.reducedMotion) return
    gsap.fromTo(el, { opacity: 0, y: 16, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'back.out(1.6)' })
    el.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turn, log.length])

  const apply = (o: Option) => {
    for (const [id, weight] of Object.entries(o.prefs ?? {})) dispatch({ type: 'pref', id, pref: { weight, from: 'answer' } })
    if (o.patch) dispatch({ type: 'set', patch: o.patch })
  }

  const answer = (label: string, opts: Option[]) => {
    if (!q) return
    opts.forEach(apply)
    dispatch({ type: 'answer', key: q.key })
    setLog((l) => [...l, { q: q.ask(trip), a: label }])
    setPicked([])
    setTurn((t) => t + 1)
  }

  const readText = () => {
    const f = fold(text)
    setGuess([...new Set(KEYWORDS.filter(([re]) => re.test(f)).map(([, id]) => id))])
  }

  const acceptGuess = () => {
    for (const id of guess) dispatch({ type: 'pref', id, pref: { weight: 'love', from: 'answer' } })
    setLog((l) => [...l, { q: q?.ask(trip) ?? '', a: text }])
    setText('')
    setGuess([])
    if (q) {
      dispatch({ type: 'answer', key: q.key })
      setTurn((t) => t + 1)
    }
  }

  return (
    <Page className="page--narrow">
      <header className="phead">
        <h1>{done ? 'Tóm tắt chuyến đi' : 'Vài câu để hiểu gu của bạn'}</h1>
        {!done && <p>Câu nào chưa chắc cứ bỏ qua. Mình chỉ hỏi điều làm thay đổi gợi ý.</p>}
      </header>

      <div className="thread" ref={thread}>
        {log.map((m, i) => (
          <div className="turn" key={i}>
            <p className="bubble bubble--q">{m.q}</p>
            <p className="bubble bubble--a">{m.a}</p>
          </div>
        ))}
        {q && (
          <div className="turn turn--live" key={q.key}>
            <p className="bubble bubble--q">{q.ask(trip)}</p>
            <div className="chips chips--answers">
              {q.options.map((o, i) =>
                q.multi ? (
                  <Chip key={o.label} on={picked.includes(i)} onClick={() => setPicked((p) => (p.includes(i) ? p.filter((x) => x !== i) : [...p, i]))}>
                    {o.label}
                  </Chip>
                ) : (
                  <Chip key={o.label} onClick={() => answer(o.label, [o])}>
                    {o.label}
                  </Chip>
                ),
              )}
            </div>
            {q.multi && (
              <button
                className="btn btn--small"
                disabled={!picked.length}
                onClick={() =>
                  answer(
                    picked.map((i) => q.options[i].label).join(', '),
                    picked.map((i) => q.options[i]),
                  )
                }
              >
                Xong câu này
              </button>
            )}
            <form
              className="freetext"
              onSubmit={(e) => {
                e.preventDefault()
                readText()
              }}
            >
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Hoặc tự viết, ví dụ: muốn săn mây và ăn đặc sản" aria-label="Tự viết câu trả lời" />
              <button type="submit" className="iconbtn" aria-label="Gửi" disabled={!text.trim()}>
                <Icon name="next" />
              </button>
            </form>
            {guess.length > 0 && (
              <div className="guess">
                <span>Mình hiểu là bạn thích: {guess.map(featureLabel).join(', ')}.</span>
                <button className="link" onClick={acceptGuess}>
                  Đúng rồi
                </button>
                <button className="link" onClick={() => setGuess([])}>
                  Không phải
                </button>
              </div>
            )}
            {text.trim() && guess.length === 0 && <p className="hint-line">Gõ xong bấm gửi, mình sẽ nói lại điều mình hiểu trước khi áp dụng.</p>}
            <div className="turn__skip">
              <button className="link" onClick={() => answer('Chưa chắc', [])}>
                Chưa chắc
              </button>
              <button className="link" onClick={() => setTurn(queue.length)}>
                Gợi ý trước đi
              </button>
            </div>
          </div>
        )}
      </div>

      {done && <Summary />}
    </Page>
  )
}

function Summary() {
  const { trip, dispatch } = useTrip()
  const loves = Object.entries(trip.prefs).filter(([, p]) => p.weight === 'love')
  const avoids = Object.entries(trip.prefs).filter(([, p]) => p.weight === 'avoid')
  const unknown = [
    !trip.lodging && 'chỗ ở (tính từ khu chợ)',
    !trip.pace && 'nhịp đi mỗi ngày',
    !loves.length && 'bạn thích gì (mình gợi ý theo nơi được nhắc nhiều)',
  ].filter(Boolean)
  const end = new Date(trip.startDate + 'T00:00:00')
  end.setDate(end.getDate() + trip.days - 1)
  const fmt = (d: Date) => d.toLocaleDateString('vi-VN', { day: 'numeric', month: 'numeric' })

  return (
    <section className="summary">
      <dl>
        <dt>Chuyến đi</dt>
        <dd>
          {trip.days} ngày, {fmt(new Date(trip.startDate + 'T00:00:00'))} đến {fmt(end)}. {trip.people} người
          {trip.who.length ? `: ${trip.who.map((w) => WHO_LABEL[w].toLowerCase()).join(', ')}` : ''}. {trip.vehicle ? VEHICLE_LABEL[trip.vehicle] : 'Chưa chọn phương tiện'}.
        </dd>
        <dt>Điểm xuất phát</dt>
        <dd>{trip.lodging ? `Gần ${placeById(trip.lodging)?.name}` : 'Khu chợ Đà Lạt'}</dd>
        <dt className="dt--rule">
          <Icon name="lock" size={14} /> Quy tắc
        </dt>
        <dd>
          Ngày 1 từ {trip.arriveAt}, rời Đà Lạt lúc {trip.leaveAt} ngày {trip.days}, mỗi ngày xong trước {trip.rules.dayEnd}
          {trip.rules.maxLegMin ? `, mỗi chặng tối đa ${trip.rules.maxLegMin} phút` : ''}
          {trip.rules.avoidSteep ? ', tránh dốc' : ''}.
          {trip.mustVisit.length > 0 && ` Phải đến: ${trip.mustVisit.map((id) => placeById(id)?.name).join(', ')}.`}
        </dd>
        <dt>Thích</dt>
        <dd className="chips">
          {loves.length
            ? loves.map(([id, p]) => (
                <span key={id} className={`chip chip--lean${p.from === 'profile' ? ' chip--profile' : ''}`}>
                  {prefLabel(id)}
                  {p.from === 'profile' && <em> từ hồ sơ của bạn</em>}
                  <button type="button" aria-label={`Bỏ ${featureLabel(id)}`} onClick={() => dispatch({ type: 'pref', id, pref: null })}>
                    <Icon name="x" size={12} />
                  </button>
                </span>
              ))
            : 'Chưa nói'}
        </dd>
        {avoids.length > 0 && (
          <>
            <dt>Muốn tránh</dt>
            <dd className="chips">
              {avoids.map(([id]) => (
                <span key={id} className="chip chip--lean">
                  {featureLabel(id)}
                  <button type="button" aria-label={`Bỏ ${featureLabel(id)}`} onClick={() => dispatch({ type: 'pref', id, pref: null })}>
                    <Icon name="x" size={12} />
                  </button>
                </span>
              ))}
            </dd>
          </>
        )}
        {unknown.length > 0 && (
          <>
            <dt>Còn chưa biết</dt>
            <dd className="muted">{unknown.join(', ')}</dd>
          </>
        )}
      </dl>
      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/setup')}>
          Sửa thông tin chuyến đi
        </button>
        <button className="btn" onClick={() => navigate('/app/shortlist')}>
          Tìm địa điểm
        </button>
      </div>
    </section>
  )
}

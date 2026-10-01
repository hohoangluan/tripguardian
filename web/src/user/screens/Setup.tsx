import { useMemo, useState } from 'react'
import { placeById, useSnapshot, VEHICLE_LABEL, type Vehicle } from '../../data/store'
import type { Place } from '../../data/types'
import { navigate } from '../../router'
import { Chip, Icon, Page, Segmented } from '../../ui/bits'
import { area, resolve, search, type MatchResult } from '../search'
import { useTrip, WHO_LABEL, type Who } from '../trip'

export function Setup() {
  const { trip, dispatch } = useTrip()
  const { snap } = useSnapshot()
  const places = snap!.places
  const missing = [!trip.who.length && 'đi với ai', !trip.vehicle && 'phương tiện'].filter(Boolean) as string[]
  const wantsImport = trip.startWith === 'saved' || trip.startWith === 'itinerary'

  const toggleWho = (w: Who) => dispatch({ type: 'set', patch: { who: trip.who.includes(w) ? trip.who.filter((x) => x !== w) : [...trip.who, w] } })

  return (
    <Page>
      <header className="phead">
        <h1>Chuyến đi của bạn</h1>
        <p>Ba điều bắt buộc, còn lại thêm khi cần. Quy tắc bạn đặt sẽ không bao giờ bị nới mà không hỏi bạn.</p>
      </header>

      <section className="block">
        <h2 className="block__title">Khi nào, bao lâu</h2>
        <div className="row">
          <label className="field">
            <span>Ngày đến</span>
            <input type="date" value={trip.startDate} onChange={(e) => dispatch({ type: 'set', patch: { startDate: e.target.value } })} />
          </label>
          <div className="field">
            <span>Số ngày</span>
            <Segmented label="Số ngày" value={trip.days} onChange={(d) => dispatch({ type: 'set', patch: { days: d } })} options={[2, 3, 4].map((d) => ({ value: d, label: `${d} ngày` }))} />
          </div>
        </div>
      </section>

      <section className="block">
        <h2 className="block__title">Đi với ai</h2>
        <div className="chips">
          {(Object.keys(WHO_LABEL) as Who[]).map((w) => (
            <Chip key={w} on={trip.who.includes(w)} onClick={() => toggleWho(w)}>
              {WHO_LABEL[w]}
            </Chip>
          ))}
        </div>
        <label className="field field--inline">
          <span>Tổng số người</span>
          <span className="stepper">
            <button type="button" aria-label="Bớt một người" onClick={() => dispatch({ type: 'set', patch: { people: Math.max(1, trip.people - 1) } })}>
              −
            </button>
            <output>{trip.people}</output>
            <button type="button" aria-label="Thêm một người" onClick={() => dispatch({ type: 'set', patch: { people: Math.min(12, trip.people + 1) } })}>
              +
            </button>
          </span>
        </label>
      </section>

      <section className="block">
        <h2 className="block__title">Đi lại bằng gì</h2>
        <Segmented
          label="Phương tiện"
          value={trip.vehicle}
          onChange={(v: Vehicle) => dispatch({ type: 'set', patch: { vehicle: v } })}
          options={(Object.keys(VEHICLE_LABEL) as Vehicle[]).map((v) => ({ value: v, label: VEHICLE_LABEL[v] }))}
        />
      </section>

      <section className="block block--rule">
        <h2 className="block__title">
          <Icon name="lock" size={16} /> Quy tắc, không vượt qua
        </h2>
        <p className="block__hint">Kế hoạch nào phá quy tắc sẽ bị báo ngay. Chỉ bạn mới nới được.</p>
        <div className="row">
          <label className="field">
            <span>Ngày 1 bắt đầu từ</span>
            <input type="time" value={trip.arriveAt} onChange={(e) => dispatch({ type: 'set', patch: { arriveAt: e.target.value } })} />
          </label>
          <label className="field">
            <span>Ngày {trip.days} rời Đà Lạt lúc</span>
            <input type="time" value={trip.leaveAt} onChange={(e) => dispatch({ type: 'set', patch: { leaveAt: e.target.value } })} />
          </label>
          <label className="field">
            <span>Mỗi ngày xong trước</span>
            <input type="time" value={trip.rules.dayEnd} onChange={(e) => dispatch({ type: 'rules', patch: { dayEnd: e.target.value } })} />
          </label>
        </div>
        <div className="field">
          <span>Mỗi chặng đi tối đa</span>
          <Segmented
            label="Mỗi chặng đi tối đa"
            value={trip.rules.maxLegMin ?? 0}
            onChange={(v) => dispatch({ type: 'rules', patch: { maxLegMin: v || null } })}
            options={[
              { value: 0, label: 'Không giới hạn' },
              { value: 20, label: '20 phút' },
              { value: 30, label: '30 phút' },
              { value: 45, label: '45 phút' },
            ]}
          />
        </div>
        <label className="toggle">
          <input type="checkbox" checked={trip.rules.avoidSteep} onChange={(e) => dispatch({ type: 'rules', patch: { avoidSteep: e.target.checked } })} />
          <span>Tránh nơi phải leo dốc hoặc nhiều bậc</span>
        </label>
        <p className="block__note">
          Ngân sách: chưa có đủ dữ liệu giá đã xác minh để kiểm tra, nên bản này chưa đặt được giới hạn chi phí.
        </p>
      </section>

      <MustVisit places={places} />

      <section className="block">
        <h2 className="block__title">Chỗ ở, nếu đã đặt</h2>
        <p className="block__hint">Chỉ dùng làm điểm bắt đầu và kết thúc mỗi ngày. Mình không gợi ý chỗ ở.</p>
        <LodgingPicker places={places} />
      </section>

      {wantsImport ? <Importer places={places} /> : null}

      <div className="pfoot">
        {missing.length > 0 && <p className="pfoot__need">Còn thiếu: {missing.join(', ')}.</p>}
        <button className="btn" disabled={missing.length > 0} onClick={() => navigate('/app/discover')}>
          Tiếp tục với sở thích
        </button>
      </div>
    </Page>
  )
}

function PlacePicker({ places, onPick, placeholder }: { places: Place[]; onPick: (p: Place) => void; placeholder: string }) {
  const [q, setQ] = useState('')
  const results = useMemo(() => search(q, places), [q, places])
  return (
    <div className="picker">
      <label className="search">
        <Icon name="search" size={16} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      </label>
      {results.length > 0 && (
        <ul className="picker__list">
          {results.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => {
                  onPick(p)
                  setQ('')
                }}
              >
                <b>{p.name}</b>
                <small>
                  {p.category} {area(p) && `ở ${area(p)}`}
                </small>
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.length >= 2 && results.length === 0 && <p className="picker__none">Không tìm thấy trong dữ liệu Đà Lạt hiện có.</p>}
    </div>
  )
}

function MustVisit({ places }: { places: Place[] }) {
  const { trip, dispatch } = useTrip()
  return (
    <section className="block block--rule">
      <h2 className="block__title">
        <Icon name="flag" size={16} /> Nhất định phải đến
      </h2>
      <div className="chips">
        {trip.mustVisit.map((id) => (
          <span className="chip chip--rule" key={id}>
            {placeById(id)?.name}
            <button
              type="button"
              aria-label="Bỏ khỏi danh sách phải đến"
              onClick={() => dispatch({ type: 'set', patch: { mustVisit: trip.mustVisit.filter((x) => x !== id), locked: trip.locked.filter((x) => x !== id) } })}
            >
              <Icon name="x" size={12} />
            </button>
          </span>
        ))}
      </div>
      <PlacePicker
        places={places}
        placeholder="Tìm tên địa điểm"
        onPick={(p) => {
          if (trip.mustVisit.includes(p.id)) return
          dispatch({ type: 'set', patch: { mustVisit: [...trip.mustVisit, p.id] } })
          dispatch({ type: 'lock', id: p.id })
        }}
      />
    </section>
  )
}

function LodgingPicker({ places }: { places: Place[] }) {
  const { trip, dispatch } = useTrip()
  const lodging = trip.lodging ? placeById(trip.lodging) : null
  if (lodging)
    return (
      <div className="anchor">
        <Icon name="pin" />
        <span>
          Tính đường đi từ gần <b>{lodging.name}</b>
        </span>
        <button className="link" onClick={() => dispatch({ type: 'set', patch: { lodging: null } })}>
          Đổi
        </button>
      </div>
    )
  return (
    <>
      <PlacePicker places={places} placeholder="Chọn một nơi gần chỗ ở của bạn" onPick={(p) => dispatch({ type: 'set', patch: { lodging: p.id } })} />
      <p className="block__note">Chưa chọn thì mình tính từ khu chợ Đà Lạt.</p>
    </>
  )
}

interface Line {
  text: string
  result: MatchResult
  chosen: string | null
  keepUnverified: boolean
}

function Importer({ places }: { places: Place[] }) {
  const { trip, dispatch } = useTrip()
  const [raw, setRaw] = useState('')
  const [lines, setLines] = useState<Line[]>([])

  const run = () => {
    const seen = new Map<string, Line>()
    for (const text of raw.split(/\n|;/).map((s) => s.trim()).filter(Boolean)) {
      const result = resolve(text, places)
      const key = result.state === 'matched' ? result.place.id : text
      if (seen.has(key)) continue // "Túi Mơ To" and "Tiệm Túi Mơ To" collapse into one row
      seen.set(key, { text, result, chosen: result.state === 'matched' ? result.place.id : null, keepUnverified: true })
    }
    setLines([...seen.values()])
  }

  const add = (l: Line) => l.chosen && dispatch({ type: 'select', id: l.chosen })

  return (
    <section className="block">
      <h2 className="block__title">Nhập địa điểm bạn đã lưu</h2>
      <p className="block__hint">Dán tên, mỗi dòng một nơi. Mình không đoán: chỗ nào chưa chắc sẽ hỏi lại bạn.</p>
      <textarea rows={4} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder={'Ví dụ:\nĐỉnh Langbiang\nThung lũng hoa cẩm tú cầu'} />
      <button className="btn btn--ghost" onClick={run} disabled={!raw.trim()}>
        Đối chiếu
      </button>
      {lines.length > 0 && (
        <ul className="imports">
          {lines.map((l, i) => (
            <li key={l.text} className={`imp imp--${l.result.state}`}>
              <span className="imp__state">
                {l.result.state === 'matched' ? <Icon name="check" size={14} /> : l.result.state === 'choose' ? <Icon name="info" size={14} /> : <Icon name="alert" size={14} />}
                {l.result.state === 'matched' ? 'Đã khớp' : l.result.state === 'choose' ? 'Cần bạn chọn' : 'Không tìm thấy'}
              </span>
              <b>{l.text}</b>
              {l.result.state === 'matched' && (
                <span className="imp__match">
                  {l.result.place.name}
                  {trip.selected.includes(l.result.place.id) ? (
                    <em>Đã thêm</em>
                  ) : (
                    <button className="link" onClick={() => add(l)}>
                      Thêm vào danh sách
                    </button>
                  )}
                </span>
              )}
              {l.result.state === 'choose' && (
                <div className="imp__cands">
                  {l.result.candidates.map((c) => (
                    <button
                      key={c.id}
                      className={`cand${l.chosen === c.id ? ' is-on' : ''}`}
                      onClick={() => {
                        const next = [...lines]
                        next[i] = { ...l, chosen: c.id }
                        setLines(next)
                        dispatch({ type: 'select', id: c.id })
                      }}
                    >
                      <b>{c.name}</b>
                      <small>
                        {c.category}, {area(c)}
                      </small>
                    </button>
                  ))}
                </div>
              )}
              {l.result.state === 'missing' && (
                <span className="imp__match">
                  Giữ lại ở dạng chưa xác minh, mình sẽ không dùng nó để xếp lịch.
                  <button className="link" onClick={() => setLines(lines.filter((_, j) => j !== i))}>
                    Xóa dòng này
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

import * as Dialog from '@radix-ui/react-dialog'
import { useMemo, useState } from 'react'
import { fmtMin, info } from '../../lib'
import type { View, Variant } from '../../planning/types'
import { PlacePhoto } from '../../ui/common'
import { Icon } from '../../ui/icons'
import { Stamp } from '../../ui/Stamp'
import { FlowBar, Page } from '../../ui/Shell'
import { LongTripWarning } from '../../ui/LongTripWarning'
import { KeepAll, NoHotel, Tradeoff } from './parts'
import { costText, placeName, visits } from './shared'

// docs/UI_SPEC_USER_WEB.md Trang 8, mẫu ui_mock_for_design/designs/itinerary: three ways to go, one photo each, the places
// each one sets aside and why. Nothing is planned until the person picks one and presses "Xem lịch trình".
// First visit: the ways sit blurred behind a postcard that says why there are several and what each one is for (gate.css
// paper); "Xem N phương án" lifts the blur. Changing a way already chosen goes straight to the cards.

const keptCount = (v: Variant) => v.metrics.places ?? v.itinerary.reduce((n, d) => n + visits(d).length, 0)

// One representative photo per way: the best-rated kept place, a different one per card when it can be.
function coverIds(variants: Variant[]) {
  const used = new Set<string>()
  return variants.map((v) => {
    const ids = v.itinerary.flatMap((d) => visits(d).map((it) => it.place_id!))
    const ranked = [...new Set(ids)].filter((id) => info(id)?.photos.length).sort((a, b) => (info(b)?.rating ?? 0) - (info(a)?.rating ?? 0))
    const id = ranked.find((x) => !used.has(x)) ?? ranked[0] ?? ids[0] ?? null
    if (id) used.add(id)
    return id
  })
}

export function Choose({ variants, keepAll, overload, locked, current, busy, hasHotel, onBack, onHotel, onPick, onCancel }: {
  variants: Variant[]; keepAll?: View['keep_all']; overload?: View['overload']; locked: string[]; current: string | null
  busy: boolean; hasHotel: boolean; onBack: () => void; onHotel: () => void; onPick: (id: string) => void; onCancel?: () => void
}) {
  const [sel, setSel] = useState<string | null>(current)
  const [cmp, setCmp] = useState(false)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [why, setWhy] = useState(!current && variants.filter((v) => v.status !== 'unavailable').length > 1)
  const covers = useMemo(() => coverIds(variants), [variants])
  const usable = (v: Variant) => v.status !== 'unavailable'
  const total = Math.max(0, ...variants.map((v) => keptCount(v) + (v.dropped_by_plan?.length ?? 0)))
  const chosen = variants.find((v) => v.id === sel)
  const lockedNames = locked.map((id) => info(id)?.name).filter((n): n is string => !!n)
  const move = (from: number, delta: number) => {
    for (let k = 1; k <= variants.length; k++) {
      const next = variants[(((from + delta * k) % variants.length) + variants.length) % variants.length]
      if (usable(next)) { setSel(next.id); document.getElementById(`tg-it-v-${next.id}`)?.focus(); return }
    }
  }
  const days = variants[0]?.itinerary.length ?? 0
  return (
    <>
      <FlowBar step="plan" />
      <div className="tg-it-crumb"><button type="button" className="tg-it-crumb__back" aria-label="Quay lại" onClick={onCancel ?? onBack}><Icon name="arrowLeft" size={18} /></button><span>Lập lịch trình</span><Icon name="chevronRight" size={14} /><strong>Chọn phương án</strong></div>
      <Page className={`tg-it-choose ${why ? 'is-why' : ''}`}>
        <header className="tg-it-title" aria-hidden={why || undefined}>
          <p className="tg-kicker">Chọn cách đi phù hợp với bạn</p>
          <h1>{overload ? 'Danh sách hơi nhiều cho số ngày này.' : `${total} nơi đã chọn. Chọn cách bạn muốn đi.`}</h1>
          <p>{overload ? `${overload.selection_places} nơi đã chọn. Mỗi hướng cho biết nơi được chừa ra và vì sao.` : 'Chọn điều bạn muốn ưu tiên. Xem những nơi tạm bỏ bên dưới; chọn xong vẫn đổi được.'}</p>
          {lockedNames.length > 0 && <span className="tg-it-title__ctx"><Icon name="lock" size={14} />Luôn giữ {lockedNames.join(', ')}</span>}
        </header>
        {!why && overload && <div className="tg-it-note is-attention" role="status"><Icon name="warn" size={18} /><span>{overload.text} Đây là ước lượng; từng lịch được kiểm tra bằng bộ lập lịch và validator.</span></div>}
        {!why && !hasHotel && <NoHotel onHotel={onHotel} />}
        {!why && <LongTripWarning days={days} />}
        <div className="tg-it-stage">
          <div className="tg-it-choices" role="radiogroup" aria-label="Chọn một phương án" aria-hidden={why || undefined} inert={why || undefined}>
            {variants.map((v, i) => {
              const on = sel === v.id
              const dropped = v.dropped_by_plan ?? []
              const shown = open[v.id] ? dropped : dropped.slice(0, 3)
              const cover = covers[i]
              const kept = keptCount(v)
              return (
                <article key={v.id} id={`tg-it-v-${v.id}`} role="radio" aria-checked={on} aria-disabled={!usable(v) || undefined} tabIndex={on || (!sel && i === 0) ? 0 : -1}
                  className={`tg-it-choice ${on ? 'is-on' : ''} ${usable(v) ? '' : 'is-off'}`} style={{ ['--i' as string]: i }}
                  onClick={() => usable(v) && setSel(v.id)}
                  onKeyDown={(e) => {
                    if (e.target !== e.currentTarget) return
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (usable(v)) setSel(v.id) }
                    else if (['ArrowRight', 'ArrowDown'].includes(e.key)) { e.preventDefault(); move(i, 1) }
                    else if (['ArrowLeft', 'ArrowUp'].includes(e.key)) { e.preventDefault(); move(i, -1) }
                  }}>
                  <div className="tg-it-choice__cover">
                    {cover ? <PlacePhoto id={cover} name={placeName(cover)} /> : <div className="tg-photo tg-photo__ph" />}
                    <span className="tg-it-choice__badge">{dropped.length ? `Tạm bỏ ${dropped.length} nơi` : 'Giữ đủ các nơi'}</span>
                    <span className="tg-it-radio" aria-hidden="true"><Icon name="check" size={15} /></span>
                    {cover && <small>Ảnh: {placeName(cover)}</small>}
                  </div>
                  <div className="tg-it-choice__body">
                    <h2>{v.label}</h2>
                    <p className="tg-it-choice__note">{v.definition ?? v.why ?? v.robustness.reasons[0] ?? ''}</p>
                    <dl className="tg-it-stats">
                      <div><dt><Icon name="pin" size={14} />Nơi ghé</dt><dd>{kept}<small> · {v.itinerary.length} ngày</small></dd></div>
                      <div><dt><Icon name="route" size={14} />Đi lại</dt><dd>≈{fmtMin(v.metrics.travel_min)}</dd></div>
                      <div><dt><Icon name="wallet" size={14} />Chi phí</dt><dd>{costText(v)}</dd></div>
                    </dl>
                    <div className="tg-it-drops">
                      {dropped.length ? <>
                        <b className="tg-it-label">Nơi tạm bỏ</b>
                        {shown.map((x) => <div key={x.place_id} className="tg-it-drop"><span aria-hidden="true">−</span><div><b>{x.name}</b><small>{x.text}</small></div></div>)}
                        {dropped.length > 3 && <button type="button" className="tg-it-textbtn" onClick={(e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [v.id]: !o[v.id] })) }}>{open[v.id] ? 'Thu gọn' : `Xem thêm ${dropped.length - 3} nơi`}</button>}
                      </> : <>
                        <b className="tg-it-label">Giữ cả {kept} nơi bạn đã chọn</b>
                        <p className="tg-faint">Không phải bỏ nơi nào.</p>
                      </>}
                    </div>
                    {v.tradeoff && <p className="tg-it-choice__trade tg-faint">Đánh đổi: {v.tradeoff}</p>}
                    {!usable(v) && <p className="tg-it-choice__trade">{v.unavailable_reason ?? 'Không tìm được lịch hợp lệ cho hướng này.'}</p>}
                    <span className="tg-it-choice__pick" aria-hidden="true">{on ? <><Icon name="check" size={16} />Đã chọn</> : 'Chọn phương án này'}</span>
                  </div>
                </article>
              )
            })}
          </div>
          {why && <section className="tg-it-why" aria-labelledby="tg-it-why-t">
            <Stamp icon="route" className="tg-it-why__stamp" />
            <p className="tg-it-why__kicker">Vì sao có {variants.length} phương án?</p>
            <h2 id="tg-it-why-t" className="tg-it-why__title">{overload ? <>{overload.selection_places} nơi khó vừa thoải mái trong {days} ngày. <em>Nên mình đưa ra {variants.length} cách đi.</em></> : <>Cùng {total} nơi, vẫn có {variants.length} cách đi. <em>Mỗi cách ưu tiên một điều.</em></>}</h2>
            <p className="tg-it-why__desc">{overload ? overload.text : 'Xếp các nơi vào từng ngày luôn phải đánh đổi: đi gọn hơn, ghé được nhiều hơn, hay chậm lại một chút. Mình không chọn thay bạn.'}</p>
            <ol className="tg-it-why__ways">{variants.filter(usable).map((v, i) => <li key={v.id}>
              <span aria-hidden="true">{i + 1}</span>
              <div><b>{v.label}</b><small>{v.definition ?? v.why ?? v.robustness.reasons[0] ?? ''}</small></div>
              <em>{v.dropped_by_plan?.length ? `Tạm bỏ ${v.dropped_by_plan.length} nơi` : `Giữ cả ${keptCount(v)} nơi`}</em>
            </li>)}</ol>
            <p className="tg-it-why__cat">{lockedNames.length ? `Luôn giữ ${lockedNames.join(', ')}` : 'Không có phương án nào đúng nhất'} · Chọn xong vẫn đổi được</p>
            <button type="button" className="tg-it-why__go" autoFocus onClick={() => setWhy(false)}>Xem {variants.filter(usable).length} phương án<Icon name="arrow" size={16} /></button>
          </section>}
        </div>
        {!why && <>
          {!variants.some(usable) && <div className="tg-it-note is-blocked"><Icon name="warn" size={18} /><span><b>Chưa tìm được hướng hợp lệ.</b> Giữ tất cả hợp lệ: {overload?.keep_all_valid ? 'có thể xem lại lịch gốc' : 'không'}.</span><button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={onBack}>Quay lại chọn nơi</button></div>}
          <div className="tg-it-help"><span>Giờ giấc, đường đi và chi phí là ước tính từ dữ liệu địa điểm.</span><button type="button" className="tg-it-textbtn" onClick={() => setCmp(true)}>So sánh chi tiết <Icon name="arrow" size={14} /></button></div>
          {keepAll && <KeepAll variant={keepAll} busy={busy} onPick={onPick} />}
        </>}
      </Page>
      {!why && <div className="tg-it-foot">
        <div className="tg-it-foot__in">
          <div className="tg-it-foot__status">{chosen ? <><b>{chosen.label}</b><span>Giữ {keptCount(chosen)} nơi · Tạm bỏ {chosen.dropped_by_plan?.length ?? 0} nơi</span></> : <span>Chọn 1 phương án để tiếp tục</span>}</div>
          <button type="button" className="tg-btn tg-btn--primary" disabled={!chosen || busy} onClick={() => chosen && onPick(chosen.id)}>Xem lịch trình <Icon name="arrow" size={18} /></button>
        </div>
      </div>}
      <Dialog.Root open={cmp} onOpenChange={setCmp}>
        <Dialog.Portal><Dialog.Overlay className="tg tg-overlay" /><Dialog.Content className="tg tg-it-dlg is-wide" aria-describedby={undefined}>
          <header><Dialog.Title>So sánh {variants.length} phương án</Dialog.Title><Dialog.Close className="tg-icon-btn" aria-label="Đóng"><Icon name="x" size={18} /></Dialog.Close></header>
          <Tradeoff variants={variants} busy={busy} active={sel} onPick={(id) => { setSel(id); setCmp(false) }} />
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </>
  )
}

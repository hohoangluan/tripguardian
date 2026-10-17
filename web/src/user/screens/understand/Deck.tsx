import { useEffect, useId, useState, type ReactNode } from 'react'
import { lodgingSuggest } from '../../tu/api'
import type { Deck, DeckAnswers, DeckIssue, LodgingHit, Option, Tab } from '../../tu/types'
import { Icon, type IconName } from '../../ui/icons'
import { CardImg, preloadPhotos } from '../../ui/common'
import { PlaceInput } from '../../ui/PlaceInput'
import { TimeInput } from '../../ui/TimeInput'
import { LodgingCards } from './LodgingCards'

const ISSUE_TEXT: Record<DeckIssue['code'], string> = {
  past_date: 'Ngày đi đã qua, bạn chọn lại nhé.',
  end_before_start: 'Ngày hoặc giờ kết thúc cần sau lúc bắt đầu.',
  too_long: 'Chuyến đi tối đa 30 ngày, bạn rút ngắn khoảng ngày nhé.',
  people_below_groups: 'Số người ít hơn các nhóm đã chọn. Mình vẫn ghi nhận, bạn kiểm tra lại nhé.',
  contradicts_said: 'Lựa chọn này khác điều bạn đã nói. Bạn xem lại lưu ý cho cả nhóm nhé.',
  invalid: 'Mình chưa đọc được câu trả lời này, bạn kiểm tra lại nhé.',
}
export function DeckIssues({ issues }: { issues: DeckIssue[] }) {
  return <>{issues.map((issue, i) => <p className="tg-warn-t" role="status" key={`${issue.key}-${i}`}>{ISSUE_TEXT[issue.code] ?? ISSUE_TEXT.invalid}</p>)}</>
}
export const clockOf = (o: Option) => o.label.match(/\b\d{2}:\d{2}\b/)?.[0]
  ?? o.description.match(/\b\d{2}:\d{2}\b/)?.[0]

const scopeIds = ['trip_total', 'per_day', 'per_person', 'per_person_day']
export const TAB_ICON: Record<string, IconName> = { trip: 'calendar', companions: 'users', mobility: 'car', care: 'heart', pace: 'gauge', budget: 'wallet', lodging: 'bed' }

// What the user chose on a deck's tabs, and the answers the server reads (one form for the gate sheet's deck and
// the chat's one-question card).
export function useDeckForm(deck: Deck, at: number) {
  const [picked, setPicked] = useState<Record<string, string[]>>(() => Object.fromEntries(deck.tabs.map(t => [t.qid, t.options.filter(o => o.prefilled).map(o => o.id)])))
  const [fields, setFields] = useState<Record<string, string>>({})
  const tab = deck.tabs[Math.min(at, deck.tabs.length - 1)]
  const selected = (tab && picked[tab.qid]) ?? []
  const field = (key: string, value: string) => setFields(old => ({ ...old, [key]: value }))
  const choose = (o: Option) => {
    setPicked(old => {
      const current = (old[tab.qid] ?? []).filter(id => id !== 'skip' && (tab.qid !== 'budget' || o.id === 'unlimited' || id !== 'unlimited'))
      const group = tab.qid === 'trip' ? o.id.split('.')[0] : tab.qid === 'budget' ? (scopeIds.includes(o.id) ? 'scope' : 'amount') : null
      const sameGroup = (id: string) => group === 'scope' ? scopeIds.includes(id) : group === 'amount' ? id.startsWith('amount.') : id.startsWith(`${group}.`)
      const multi = tab.multi && !(tab.qid === 'care' && o.id === 'none') && !(tab.qid === 'companions' && o.id === 'solo')
      const base = group ? current.filter(id => !sameGroup(id)) : multi ? current.filter(id => id !== 'none' && id !== 'solo') : []
      return { ...old, [tab.qid]: current.includes(o.id) ? base.filter(id => id !== o.id) : [...base, o.id] }
    })
    if (tab.qid === 'trip') {
      const part = o.id.split('.')[0]
      if (part === 'start' || part === 'end') field(`trip.${part}`, selected.includes(o.id) ? '' : clockOf(o) ?? '')
      if (part === 'dates') setFields(({ dateFrom: _, dateTo: __, ...rest }) => rest)
    }
    if (tab.qid === 'budget') field('budget.unlimited', o.id === 'unlimited' && !selected.includes(o.id) ? 'true' : '')
    if (o.id === 'people.prefilled') field('companions.people', '')
    if (o.id === 'amount.prefilled') field('budget.amount', '')
    if (tab.qid === 'lodging') field('lodging', '')
  }
  const skip = () => setPicked(old => ({ ...old, [tab.qid]: ['skip'] }))
  const toggleInput = (key: string, value: string, group: string) => {
    field(key, value)
    if (key === 'budget.amount') field('budget.unlimited', '')
    setPicked(old => ({ ...old, [tab.qid]: (old[tab.qid] ?? []).filter(id => id !== 'skip' && !(tab.qid === 'budget' && id === 'unlimited') && !id.startsWith(group)) }))
  }
  const pickLodging = (h: LodgingHit) => {
    field('lodging', JSON.stringify({ kind: h.kind, ...(h.id ? { id: h.id } : {}), text: h.text, lat: h.lat, lng: h.lng }))
    setPicked(old => ({ ...old, lodging: [] }))
  }
  const answers: DeckAnswers = {}
  for (const t of deck.tabs) {
    const ids = picked[t.qid] ?? []
    const has = (id: string) => ids.includes(id)
    if (has('skip')) { answers[t.qid] = ['skip']; continue }
    if (t.kind !== 'required' || !['trip', 'companions', 'budget', 'lodging'].includes(t.qid)) {
      if (ids.length) answers[t.qid] = ids
    } else if (t.qid === 'trip') {
      if (fields.dateFrom && fields.dateTo) answers['trip.dates'] = `${fields.dateFrom}..${fields.dateTo}`
      else if (has('dates.prefilled')) answers.trip = ['dates.prefilled']
      for (const slot of ['start', 'end']) {
        const value = fields[`trip.${slot}`] ?? clockOf(t.options.find(o => ids.includes(o.id) && o.id.startsWith(`${slot}.`)) ?? { label: '', description: '', id: '' } as Option)
        if (value) answers[`trip.${slot}`] = value
      }
    } else if (t.qid === 'companions') {
      const who = ids.filter(id => id !== 'people.prefilled')
      if (who.length) answers['companions.who'] = who
      if (fields['companions.people']) answers['companions.people'] = fields['companions.people']
      else if (has('people.prefilled')) answers.companions = ['people.prefilled']
    } else if (t.qid === 'budget') {
      if (fields['budget.unlimited'] === 'true' || has('unlimited')) answers['budget.unlimited'] = 'true'
      else {
        const amount = Number(fields['budget.amount']?.replace(',', '.'))
        if (Number.isFinite(amount) && amount > 0) answers['budget.amount'] = String(Math.round(amount * 1_000_000))
        else if (has('amount.prefilled')) answers.budget = ['amount.prefilled']
        const scope = ids.find(id => scopeIds.includes(id))
        if (scope) answers['budget.scope'] = scope
      }
    } else if (fields.lodging) answers.lodging = fields.lodging
    else if (ids.length) answers.lodging = ids
  }
  return { tab, picked, selected, fields, choose, skip, toggleInput, pickLodging, answers }
}
export type DeckForm = ReturnType<typeof useDeckForm>

// The free inputs a required tab carries next to its options: dates and hours, how many people, an amount, a stay.
export function TripInputs({ form, busy, chips }: { form: DeckForm; busy: boolean; chips: (options: Option[]) => ReactNode }) {
  const { tab, fields, selected, toggleInput } = form
  const normal = tab.options.filter(o => !['other', 'skip'].includes(o.id))
  return <>
    {tab.inputs.includes('dates') && <div className="tg-full__edit"><label>Ngày đến<input className="tg-line-input" type="date" disabled={busy} value={fields.dateFrom ?? ''} onChange={e => toggleInput('dateFrom', e.target.value, 'dates.')} /></label><label>Ngày về<input className="tg-line-input" type="date" disabled={busy} value={fields.dateTo ?? ''} onChange={e => toggleInput('dateTo', e.target.value, 'dates.')} /></label></div>}
    {normal.some(o => o.id.startsWith('dates.')) && chips(normal.filter(o => o.id.startsWith('dates.')))}
    {['start', 'end'].filter(slot => tab.inputs.includes(slot)).map(slot => <div className="tg-ask__find" key={slot}>
      <label>{slot === 'start' ? 'Ngày đầu bắt đầu lúc' : 'Ngày cuối kết thúc lúc'}<TimeInput className="tg-line-input" label={slot === 'start' ? 'Ngày đầu bắt đầu lúc' : 'Ngày cuối kết thúc lúc'} disabled={busy} value={fields[`trip.${slot}`] ?? clockOf(normal.find(o => selected.includes(o.id) && o.id.startsWith(`${slot}.`)) ?? { label: '', description: '', id: '' } as Option) ?? ''} onChange={v => toggleInput(`trip.${slot}`, v, `${slot}.`)} /></label>
      {chips(normal.filter(o => o.id.startsWith(`${slot}.`)))}
    </div>)}
  </>
}

// send: the chat's card answers at once when a stay is tapped; the gate keeps the pick on the form (its tab gets a tick). ranked: places are chosen, so stays are listed around them.
export function ExtraInputs({ form, busy, send, ranked = false }: { form: DeckForm; busy: boolean; send?: (answers: DeckAnswers, shown: string) => void; ranked?: boolean }) {
  const { tab, fields, selected, toggleInput, pickLodging, skip } = form
  const budgetAmount = Number(fields['budget.amount']?.replace(',', '.'))
  // A couple or one person is two or one: the head count is asked only once a bigger group is picked (or when only
  // the count is open, the group already known). Nothing picked yet: nothing to count.
  const who = selected.filter(id => id !== 'people.prefilled')
  const alone = who.length === 1 && who[0] === 'solo'
  const couple = who.length > 0 && who.every(id => id === 'partner')
  const askCount = tab.qid === 'companions' && tab.inputs.includes('people') && (!tab.inputs.includes('who') || (who.length > 0 && !alone && !couple))
  const people = Number(fields['companions.people'])
  return <>
    {askCount && <div className="tg-qa__chips tg-qa__counts" role="group" aria-label="Số người nhanh">
      {[2, 3, 4, 5, 6].map(n => <button type="button" key={n} className={`tg-qa__chip ${people === n ? 'is-on' : ''}`} disabled={busy} aria-pressed={people === n} onClick={() => toggleInput('companions.people', String(n), 'people.')}>{n} người</button>)}
    </div>}
    {askCount && <label className="tg-ask__date">Hoặc nhập số khác<span>
      <button type="button" disabled={busy || Number(fields['companions.people']) <= 1} aria-label="Bớt một người" onClick={() => toggleInput('companions.people', String(Math.max(1, Number(fields['companions.people']) - 1)), 'people.') }><Icon name="minus" size={16} /></button>
      <input className="tg-line-input" type="number" aria-label="Tổng số người" min="1" step="1" disabled={busy} value={fields['companions.people'] ?? ''} placeholder="Số người" onChange={e => toggleInput('companions.people', e.target.value, 'people.')} />
      <button type="button" disabled={busy} aria-label="Thêm một người" onClick={() => toggleInput('companions.people', String(Number(fields['companions.people'] || 0) + 1), 'people.')}><Icon name="plus" size={16} /></button>
    </span></label>}
    {tab.qid === 'budget' && tab.inputs.includes('amount') && <div className="tg-ask__find">
      <label>Ngân sách (triệu đồng)<input className="tg-line-input" type="text" inputMode="decimal" disabled={busy || selected.includes('unlimited') || fields['budget.unlimited'] === 'true'} value={fields['budget.amount'] ?? ''} placeholder="Ví dụ: 25 hoặc 2,5" onChange={e => toggleInput('budget.amount', e.target.value, 'amount.')} /><output aria-live="polite">{budgetAmount > 0 && Number.isFinite(budgetAmount) ? `= ${budgetAmount.toLocaleString('vi-VN')} triệu` : 'Nhập số tiền tính theo triệu đồng'}</output></label>
    </div>}
    {tab.qid === 'lodging' && <div className="tg-ask__find">
      <LodgingCards ranked={ranked} busy={busy} onAuto={() => send ? send({ lodging: ['skip'] }, 'Cứ xếp giúp') : skip()}
        onPick={p => { const hit = { kind: p.kind, id: p.id, text: p.text, lat: p.lat as number, lng: p.lng as number }; if (send) send({ lodging: JSON.stringify(hit) }, p.text); else pickLodging(hit as LodgingHit) }}
        typed={<PlaceInput<LodgingHit> label="Nơi bạn lưu trú" placeholder="Tên khách sạn, homestay hoặc địa chỉ" icon="bed" disabled={busy} fetcher={lodgingSuggest}
          row={h => ({ key: h.id ?? `${h.lat},${h.lng}`, icon: 'bed', name: h.text, sub: h.address, rating: h.rating })}
          onPick={h => { if (send) send({ lodging: JSON.stringify({ kind: h.kind, ...(h.id ? { id: h.id } : {}), text: h.text, lat: h.lat, lng: h.lng }) }, h.text); else pickLodging(h) }} />} />
      {fields.lodging && <small><Icon name="check" size={14} /> Đã chọn chỗ ở: {JSON.parse(fields.lodging).text}</small>}
    </div>}
  </>
}

// Every missing topic at once, as tabs: the read-back gate before planning (the chat asks one question at a time).
export function DeckCard({ deck, busy, issues = [], onAnswer, onOther, focus }: {
  deck: Deck; busy: boolean; issues?: DeckIssue[]; focus?: { qid: string; n: number } | null
  onAnswer: (answers: DeckAnswers) => void
  onOther: () => void
}) {
  const uid = useId()
  const [at, setAt] = useState(0)
  const form = useDeckForm(deck, at)
  const { tab, selected, choose, skip, answers } = form
  useEffect(() => {
    if (!focus) return
    const index = deck.tabs.findIndex(t => t.qid === focus.qid)
    if (index >= 0) setAt(index)
  }, [focus, deck.tabs])
  useEffect(() => preloadPhotos(deck.tabs.flatMap(t => t.options.map(o => o.photo?.url))), [deck.tabs])
  if (!tab) return null
  const chips = (options: Option[]) => <div className="tg-opts">{options.map(o => <button type="button" key={o.id} className={`tg-opt ${selected.includes(o.id) ? 'is-on' : ''}`} disabled={busy} aria-pressed={selected.includes(o.id)} title={o.description || undefined} onClick={() => choose(o)}>
    <b>{o.prefilled && <span aria-label="Mình đoán">✎ </span>}{o.label}</b>
    {o.description && <span>{o.description}</span>}
  </button>)}</div>
  const normal = tab.options.filter(o => !['other', 'skip'].includes(o.id))
  const reasons = tab.options.filter(o => o.prefilled && selected.includes(o.id) && o.because).map(o => o.because)
  const notes = issues.filter(i => i.key === tab.qid || i.key.startsWith(`${tab.qid}.`))
  const remainingNotes = issues.filter(i => !deck.tabs.some(t => i.key === t.qid || i.key.startsWith(`${t.qid}.`)))
  return <section data-deck-qid={tab.qid} className={`tg-deck ${busy ? 'is-waiting' : ''}`} aria-label="Câu hỏi về chuyến đi" aria-busy={busy}>
    <div className="tg-deck__ghost tg-deck__ghost--1" aria-hidden="true" />
    <div className="tg-deck__ghost tg-deck__ghost--2" aria-hidden="true" />
    <div className="tg-ask__card">
    <div className="tg-ask__top"><span className="tg-ask__ico"><Icon name={TAB_ICON[tab.qid] ?? 'sparkle'} size={22} /></span><div className="tg-ask__intent"><b>{tab.header}</b><span>{at + 1}/{deck.tabs.length}</span></div></div>
    <div className="tg-basics__chips" role="tablist" aria-label="Nhóm câu hỏi">{deck.tabs.map((t: Tab, i) => <button type="button" className={`tg-chip ${i === at ? 'is-on' : ''}`} role="tab" id={`${uid}-tab-${i}`} aria-controls={`${uid}-panel-${i}`} aria-selected={i === at} tabIndex={i === at ? 0 : -1} key={t.qid} disabled={busy} onClick={() => setAt(i)} onKeyDown={e => {
      const next = e.key === 'ArrowRight' ? (i + 1) % deck.tabs.length : e.key === 'ArrowLeft' ? (i - 1 + deck.tabs.length) % deck.tabs.length : e.key === 'Home' ? 0 : e.key === 'End' ? deck.tabs.length - 1 : null
      if (next === null) return
      e.preventDefault(); setAt(next); document.getElementById(`${uid}-tab-${next}`)?.focus()
    }}><span aria-hidden="true">{i + 1}</span>{t.header}{Object.keys(answers).some(k => k === t.qid || k.startsWith(`${t.qid}.`)) && <Icon name="check" size={13} />}</button>)}</div>
    <div role="tabpanel" id={`${uid}-panel-${at}`} aria-labelledby={`${uid}-tab-${at}`} className="tg-ask__panel">
      <div className="tg-ask__scroll">
      <h4 className="tg-ask__q">{tab.question}</h4>{tab.why && <p className="tg-ask__why">{tab.why}</p>}
      {tab.multi && <small className="tg-muted">Bạn có thể chọn nhiều ý</small>}
      {tab.qid === 'trip' && tab.kind === 'required' ? <TripInputs form={form} busy={busy} chips={chips} />
       : tab.visual ? <div className="tg-cx__opts">{normal.map(o => <button type="button" className={`tg-cx__opt ${selected.includes(o.id) ? 'is-on' : ''}`} key={o.id} disabled={busy} aria-pressed={selected.includes(o.id)} onClick={() => choose(o)}>
        <span className="tg-cx__pics"><span className="tg-cx__pic is-big">{o.photo ? <CardImg src={o.photo.url} alt={o.photo.name} /> : <span className="tg-muted">Chưa có ảnh</span>}</span><span className="tg-cx__ring"><Icon name="check" size={16} /></span></span>
        <span className="tg-cx__opt-b"><b>{o.prefilled ? '✎ ' : ''}{o.label}</b><small>{o.count !== null ? `${o.count.toLocaleString('vi-VN')} nơi` : ''}{o.photo?.name ? ` · ${o.photo.name}` : ''}</small></span>
      </button>)}</div> : chips(normal)}
      {!!reasons.length && <p className="tg-muted">✎ {Array.from(new Set(reasons)).join(' · ')}</p>}
      <ExtraInputs form={form} busy={busy} />
      <DeckIssues issues={notes} />
      <div className="tg-opts">{tab.options.some(o => o.id === 'other') && <button type="button" className="tg-opt is-soft" disabled={busy} onClick={onOther}>Khác, tự gõ</button>}
        {tab.options.some(o => o.id === 'skip') && <button type="button" className="tg-opt is-soft" disabled={busy} onClick={() => { skip(); if (at < deck.tabs.length - 1) setAt(at + 1) }}>Bỏ qua{selected.includes('skip') ? ' ✓' : ''}</button>}
      </div>
      </div>
      <span className="tg-ask__pill">Còn {deck.left}/{deck.total}<span className="tg-ask__meter"><i style={{ width: `${deck.total ? (deck.total - deck.left) / deck.total * 100 : 0}%` }} /></span></span>
    </div>
    <DeckIssues issues={remainingNotes} />
    <footer className="tg-ask__foot"><small>✎ là gợi ý, bạn có thể đổi.</small><div>{at < deck.tabs.length - 1 && <button type="button" className="tg-btn tg-btn--ghost" disabled={busy} onClick={() => setAt(at + 1)}>Tiếp <Icon name="chevronRight" size={15} /></button>}<button type="button" className="tg-btn tg-btn--primary" disabled={busy || !Object.keys(answers).length} onClick={() => onAnswer(answers)}>Xong <Icon name="check" size={16} /></button></div></footer>
    </div>
    {busy && <div className="tg-deck__wait" role="status"><span className="tg-dots"><i /><i /><i /></span><p>Đang ghi nhận lựa chọn của bạn…</p></div>}
  </section>
}

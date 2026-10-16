import { useEffect, useState, type CSSProperties } from 'react'
import type { Card, Deck, DeckAnswers, DeckIssue, Step, WebSource } from '../../tu/types'
import { Icon } from '../../ui/icons'
import { AskCard, PhotoStage } from './Ask'
import { CardView, type Answer } from './Cards'
import { DeckIssues } from './Deck'

// One message of the conversation. A bot turn shows, in order: what it is doing (steps, from the server's progress
// events; folded once the turn ends), what it says, and at most one question: its words as a line of the chat, then
// the card to answer it (a short numbered list, or the photo stage). The question is part of the bot's message, in
// the same bubble as its words, like a friend texting. An answered card folds into one line.

export type Msg =
  | { key: string; who: 'me'; text: string; photo?: string; files?: string[] }
  | { key: string; who: 'bot'; say: string; steps: Step[]; sources: WebSource[]; card: Card | Deck | null; answered: string | null; issues?: DeckIssue[]
      live: boolean; t0: number; t1?: number }

export const botMsg = (key: string, patch: Partial<Extract<Msg, { who: 'bot' }>> = {}): Msg =>
  ({ key, who: 'bot', say: '', steps: [], sources: [], card: null, answered: null, live: false, t0: Date.now(), ...patch })

// What the block is doing, in one line: how many things it has written down from the message so far, or what it
// reads. The count grows live as each item streams in (one line per kind, the user's own words on it). Once the turn
// ends it folds to one quiet line ("Đã xử lý trong 13 giây"), so the chat stays short; a click opens it again.
function headline(steps: Step[], live: boolean, secs: number) {
  const noted = steps.filter((s) => s.id.startsWith('rec:') || s.id.startsWith('dish:') || s.id.startsWith('kind:')).length
  if (!live) return `Đã xử lý trong ${secs < 60 ? `${secs} giây` : `${Math.floor(secs / 60)} phút ${secs % 60} giây`}`
  if (steps.some((s) => s.id.startsWith('web') && s.status === 'run')) return 'Đang tìm hiểu trên web'
  if (noted) return `Đang ghi nhận ${noted} ý từ tin nhắn`
  return steps.some((s) => s.id === 'split') ? 'Đang tách các ý trong tin nhắn' : 'Đang đọc tin nhắn'
}

function Steps({ steps, sources, live, secs }: { steps: Step[]; sources: WebSource[]; live: boolean; secs: number }) {
  const [open, setOpen] = useState(true)
  useEffect(() => {
    if (live) return setOpen(true)
    const t = window.setTimeout(() => setOpen(false), 700)
    return () => window.clearTimeout(t)
  }, [live])
  return (
    <div className={`tg-cx__think ${open ? 'is-open' : ''} ${live ? 'is-run' : ''}`}>
      <button type="button" className="tg-cx__think-h" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {live && <span className="tg-cx__spark"><Icon name="sparkle" size={17} /></span>}
        <span className={live ? 'tg-cx__shimmer' : ''} role="status" aria-atomic="true">{headline(steps, live, secs)}</span>
        <Icon name="chevronDown" size={15} className="tg-cx__chev" />
      </button>
      <div className="tg-cx__think-b"><div>
        <ol className="tg-cx__steps">
          {steps.map((s) => (
            <li key={s.id} className={`is-${s.status}`}>
              <i className="tg-cx__dot" aria-hidden="true" />
              {(() => {
                const at = s.label.indexOf(' · ')
                return at < 0 ? <b>{s.label}</b> : <><b>{s.label.slice(0, at)}</b><span className="tg-cx__said">{s.label.slice(at + 3)}</span></>
              })()}
              {s.id.startsWith('web') && sources.length > 0 && (
                <span className="tg-cx__det">{sources.map((x, i) => <a key={x.url} className="tg-cx__tag" style={{ '--d': `${i * 120}ms` } as CSSProperties} href={x.url} target="_blank" rel="noopener noreferrer">{x.domain}</a>)}</span>
              )}
            </li>
          ))}
        </ol>
      </div></div>
    </div>
  )
}

export function Turn({ m, busy, onAnswer, onDeck, onText, onPhoto }: { m: Msg; busy: boolean; onAnswer: (m: Msg, ...a: Parameters<Answer>) => void; onDeck: (m: Msg, answers: DeckAnswers, shown: string) => void; onText: (text: string) => void; onPhoto: () => void }) {
  if (m.who === 'me')
    return (
      <li className="tg-cx__m is-me">
        <div className={`tg-cx__bub ${m.photo ? 'is-img' : ''}`}>
          {m.photo && <img src={m.photo} alt="Ảnh bạn gửi" />}
          {m.text && <p>{m.text}</p>}
          {m.files?.length ? <p className="tg-cx__files">{m.files.map((n) => <span key={n}><Icon name="clip" size={13} />{n}</span>)}</p> : null}
        </div>
        <span className="tg-cx__avatar" aria-hidden="true" />
      </li>
    )
  const secs = Math.max(1, Math.round(((m.t1 ?? Date.now()) - m.t0) / 1000))
  const waiting = m.live && !m.say && !m.steps.length
  const tab = m.card?.kind === 'deck' ? m.card.tabs[0] : undefined
  return (
    <li className="tg-cx__m is-bot" aria-busy={m.live}>
      <span className="tg-cx__avatar is-bot" aria-hidden="true" />
      <div className="tg-cx__stack">
        {m.steps.length > 0 && <Steps steps={m.steps} sources={m.sources} live={m.live} secs={secs} />}
        {waiting && <p className="tg-cx__say is-wait"><span className="tg-dots" aria-hidden="true"><i /><i /><i /></span><span className="tg-sr">Đang đọc</span></p>}
        {(m.say || tab) && (
          <div className="tg-cx__say">
            {m.say && <p>{m.say}</p>}
            {tab && <p className="tg-cx__say-ask">{tab.question}</p>}
          </div>
        )}
        {m.card && m.card.kind !== 'deck' && m.card.text && m.card.qid !== 'conversation' && (
          <p className="tg-cx__q">{m.card.text}{m.card.reason && !m.answered && <small>Vì sao hỏi: {m.card.reason}</small>}</p>
        )}
        {m.card && (m.card.kind === 'deck' ? !!tab : m.card.qid !== 'conversation') && (m.answered
          ? <span className="tg-cx__done-row"><Icon name="check" size={15} />{m.answered}</span>
          : m.card.kind === 'deck' ? (tab!.visual
            ? <PhotoStage key={JSON.stringify(m.card)} deck={m.card} busy={busy} onAnswer={(answers, shown) => onDeck(m, answers, shown)} onText={onText} />
            : <AskCard key={JSON.stringify(m.card)} deck={m.card} busy={busy} issues={m.issues} onAnswer={(answers, shown) => onDeck(m, answers, shown)} onText={onText} />)
          : <CardView card={m.card} busy={busy} onAnswer={(input, shown) => onAnswer(m, input, shown)} onPhoto={onPhoto} />)}
        {(!m.card || m.answered) && <DeckIssues issues={m.issues ?? []} />}
      </div>
    </li>
  )
}

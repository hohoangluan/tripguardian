import { useEffect, useState, type ReactNode } from 'react'
import { initialOf, useAccount } from '../account'
import { enterStage, requestStageEntry, resumeJourney, type Stage } from '../journey'
import { STEPS, useTrip, type StepId } from '../trip'
import { go, href, Link } from './common'
import { Icon, Logo } from './icons'

function Me({ className }: { className: string }) {
  const account = useAccount()
  const initial = initialOf(account)
  return <Link to="/profile" className={className} aria-label={account?.guest ? 'Bạn đang dùng với tư cách khách' : 'Hồ sơ của bạn'}>{account?.avatar ? <img src={account.avatar} alt="" referrerPolicy="no-referrer" /> : initial ? <span>{initial}</span> : <Icon name="user" size={18} />}</Link>
}

const STAGE_OF: Record<StepId, Stage> = { understand: 'trip', explore: 'decision', plan: 'planning' }
const ORDER: Record<Stage, number> = { trip: 0, decision: 1, planning: 2 }

// A finished step is a way back: the journey on the server steps back with it (never forward).
// A later step is a way ahead without finishing this one: `onAhead` lets the screen move the journey on itself
// (Tìm hiểu hands what it has to Lựa chọn); without it the step's page opens and says what it still needs.
export function FlowBar({ step, aside, onAhead }: { step: StepId | 'done'; aside?: ReactNode; onAhead?: (target: StepId) => void }) {
  const { trip, dispatch } = useTrip()
  const [going, setGoing] = useState<StepId | null>(null) // the step clicked while the server steps the journey back: it shows at once
  const idx = step === 'done' ? STEPS.length : STEPS.findIndex((s) => s.id === step) // feedback comes after the last step
  const back = async (target: StepId, to: string) => {
    if (going) return
    setGoing(target)
    try { await stepBack(target, to) } finally { setGoing(null) }
  }
  const stepBack = async (target: StepId, to: string) => {
    const id = trip.journeyId
    if (id) {
      const origin = location.pathname + location.search
      const stage = STAGE_OF[target]
      try {
        const current = (await resumeJourney(id)).view
        if (origin !== location.pathname + location.search) return
        if (ORDER[stage] < ORDER[current.stage]) {
          await enterStage(id, stage)
          dispatch({ type: 'set', patch: { planningId: null, ...(stage === 'trip' ? { decisionId: null } : {}) } })
        }
        if (stage === 'trip') requestStageEntry(id, 'trip')
      } catch {
        /* the target screen shows the connection error itself */
      }
      if (origin !== location.pathname + location.search) return
    }
    go(to)
  }
  return (
    <header className="tg-flowbar">
      <Link to="/" className="tg-flowbar__logo" aria-label="Về Khám phá"><Logo size={30} /></Link>
      <ol className="tg-steps" aria-label="Tiến trình chuyến đi">
        {STEPS.map((s, i) => {
          const state = going ? (s.id === going ? 'now' : 'next') : i < idx ? 'done' : i === idx ? 'now' : 'next'
          return (
            <li key={s.id} className={`is-${state}`} aria-busy={going === s.id || undefined}>
              {state === 'done' ? (
                <a href={href(s.path)} onClick={(e) => { e.preventDefault(); back(s.id, s.path) }} className="tg-steps__a"><i><Icon name="check" size={14} /></i>{s.label}<span className="tg-sr"> (đã xong, bấm để quay lại)</span></a>
              ) : state === 'next' ? (
                <a href={href(s.path)} onClick={(e) => { e.preventDefault(); if (onAhead) onAhead(s.id); else go(s.path) }} className="tg-steps__a"><i>{i + 1}</i>{s.label}<span className="tg-sr"> (bấm để sang bước này)</span></a>
              ) : (
                <span className="tg-steps__a" aria-current="step"><i>{i + 1}</i>{s.label}</span>
              )}
            </li>
          )
        })}
      </ol>
      <div className="tg-flowbar__ops">
        {aside}
        <Me className="tg-flowbar__me" />
      </div>
    </header>
  )
}

export function Page({ children, className = '', narrow = false }: { children: ReactNode; className?: string; narrow?: boolean }) {
  return <div className={`tg-page ${narrow ? 'is-narrow' : ''} ${className}`}>{children}</div>
}

export function useTitle(t: string) {
  useEffect(() => { document.title = `${t} · TripGuardian` }, [t])
}

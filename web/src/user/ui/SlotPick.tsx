import * as Popover from '@radix-ui/react-popover'
import { useState, type ReactNode } from 'react'
import { rankOptions, type MealOption } from '../planning/view'
import { FitStars } from './FitStars'
import { Link, placeHref, PlacePhoto } from './common'

type Fit = { stars: number; level: string } | null | undefined

// A timed block the plan only suggests for (a free meal, the evening after the day): its trigger pulses so the reader
// knows there is something to choose, and opens the places in order of Card.fit, then of the shorter way.
// A suggestion is never added to the plan; choosing opens the place.
export function SlotPick({ title, options, fitOf, className = '', children }: { title: string; options: MealOption[]; fitOf: (id: string) => Fit; className?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const ranked = rankOptions(options, fitOf)
  const anyFit = ranked.some((o) => fitOf(o.place_id))
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button type="button" className={`tg-pulse ${className}`} aria-haspopup="dialog">{children}</button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="tg tg-slotpick" side="bottom" align="start" sideOffset={8} collisionPadding={12} aria-label={title}>
          <h4>{title}</h4>
          <ol>
            {ranked.map((o) => {
              const f = fitOf(o.place_id)
              return (
                <li key={o.place_id}>
                  <Link to={placeHref(o.place_id)} className="tg-slotpick__row">
                    <PlacePhoto id={o.place_id} name={o.name} className="tg-slotpick__ph" />
                    <span>
                      <b>{o.name}</b>
                      <small>{f ? <><FitStars stars={f.stars} /> {f.level} với bạn</> : 'Chưa so được độ hợp với bạn'}</small>
                      <small className="tg-faint">Cách {o.km.toLocaleString('vi-VN')} km</small>
                    </span>
                  </Link>
                </li>
              )
            })}
          </ol>
          <p className="tg-faint">{anyFit ? 'Xếp theo độ hợp với bạn, rồi theo đường đi gần nhất.' : 'Xếp theo đường đi gần nhất.'} Gợi ý, chưa nằm trong lịch.</p>
          <Popover.Arrow className="tg-slotpick__arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

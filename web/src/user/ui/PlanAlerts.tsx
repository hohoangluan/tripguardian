import { useState } from 'react'
import type { Alert } from '../planning/view'
import { Icon } from './icons'

// What to check before going, above the journey where it cannot be missed: the worst first, each with the day it
// concerns, three shown and the rest one tap away. No notice is not "all clear", and the strip says exactly that.
const SHOWN = 3

export function PlanAlerts({ alerts }: { alerts: Alert[] }) {
  const [all, setAll] = useState(false)
  const warns = alerts.filter((a) => a.level === 'warn').length
  if (!alerts.length)
    return <p className="tg-alerts__none" data-tour="plan-alerts"><Icon name="info" size={16} /> Chưa có thông báo hay sự kiện ghi nhận cho chuyến này (không có nghĩa là chắc chắn bình thường).</p>
  const rows = all ? alerts : alerts.slice(0, SHOWN)
  return (
    <section className={`tg-alerts ${warns ? 'is-warn' : ''}`} aria-labelledby="tg-alerts-h" data-tour="plan-alerts">
      <h2 id="tg-alerts-h"><Icon name={warns ? 'warn' : 'info'} size={18} /> {warns ? `Cần để ý trước khi đi · ${warns}` : 'Lưu ý cho chuyến này'}</h2>
      <ul>
        {rows.map((a) => (
          <li key={a.key} className={`is-${a.level}`}>
            <i aria-hidden="true"><Icon name={a.icon} size={16} /></i>
            <p>
              {a.day != null && <em className="tg-tag">Ngày {a.day}</em>}
              {a.lead && <b>{a.lead}{a.lead.endsWith(')') ? '. ' : ': '}</b>}{a.text}
            </p>
          </li>
        ))}
      </ul>
      {alerts.length > SHOWN && <button type="button" className="tg-link" aria-expanded={all} onClick={() => setAll((v) => !v)}>{all ? 'Thu gọn' : `Xem thêm ${alerts.length - SHOWN} lưu ý`}</button>}
    </section>
  )
}

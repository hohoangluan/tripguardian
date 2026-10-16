import { useState } from 'react'
import { FAQ } from '../faq'
import { openCreate } from '../home/dialogs'
import { Icon } from '../ui/icons'
import { Link } from '../ui/common'
import { Page, useTitle } from '../ui/Shell'

const STEPS: [string, string][] = [
  ['Tìm hiểu', 'Bạn kể chuyến đi bằng chat hoặc chọn nhanh; TripGuardian hỏi thêm cho đúng ý.'],
  ['Lựa chọn', 'Bạn xem từng nơi cùng lý do vì sao hợp, rồi tự chọn. Không nơi nào bị chặn.'],
  ['Lịch trình', 'TripGuardian xếp lịch từng giờ theo nơi bạn chọn; bạn đổi, kéo thả, thêm bớt tùy ý.'],
  ['Đánh giá', 'Sau chuyến, bạn cho biết gợi ý có đúng gu để lần sau hợp hơn.'],
]

// "Hỗ trợ": how the app works and the questions people ask, written once in faq.ts.
export function Support() {
  useTitle('Hỗ trợ')
  const [open, setOpen] = useState(0)
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Trung tâm trợ giúp</p><h1>Hỗ trợ</h1><p>Cách TripGuardian làm việc và những câu bạn hay hỏi.</p></div></header>
      <ol className="tg-sup__steps">
        {STEPS.map(([t, d], i) => <li key={t}><i>{i + 1}</i><b>{t}</b><p>{d}</p></li>)}
      </ol>
      <section className="tg-sup__faq" aria-labelledby="tg-sup-h">
        <h2 id="tg-sup-h">Hỏi nhanh</h2>
        {FAQ.map(([q, a], i) => (
          <div key={q} className="tg-sup__q">
            <button type="button" aria-expanded={open === i} onClick={() => setOpen(open === i ? -1 : i)}>{q}<Icon name={open === i ? 'minus' : 'plus'} size={17} /></button>
            <div className="tg-sup__a" data-open={open === i}><p>{a}</p></div>
          </div>
        ))}
      </section>
      <p className="tg-sup__go">
        <button type="button" className="tg-btn tg-btn--primary" onClick={() => openCreate()}><Icon name="plus" size={16} />Tạo chuyến mới</button>
        <Link to="/profile" className="tg-btn tg-btn--ghost">Chỉnh hồ sơ</Link>
      </p>
    </Page>
  )
}

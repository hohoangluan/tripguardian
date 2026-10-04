import { Icon, Page } from '../../ui/bits'

// Explore is a way into the flow ("8 chỗ trong nhà khi mưa" -> a shortlist), not a magazine. Not built yet:
// the slots are there, each says it is coming.
export const EXPLORE = [
  { title: 'Theo khu', note: 'Trại Mát, Cầu Đất, quanh hồ', icon: 'map' },
  { title: 'Đi lúc mưa', note: 'chỗ trong nhà, vẫn đẹp', icon: 'rain' },
  { title: 'Buổi sáng sớm', note: 'nơi vắng trước 8 giờ', icon: 'sun' },
]

export function Explore() {
  return (
    <Page className="page--mid">
      <header className="uhead">
        <h1>Khám phá Đà Lạt</h1>
        <p>Mỗi chủ đề sẽ mở thẳng thành một danh sách gợi ý cho chuyến của bạn. Phần này chưa mở.</p>
      </header>
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
    </Page>
  )
}

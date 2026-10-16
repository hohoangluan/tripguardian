import { info } from '../lib'
import { openTheme } from '../home/dialogs'
import { themeOf } from '../home/themes'
import { useWarm } from '../../data/store'
import { useUi } from '../store'
import { ArtCup, Empty, go, PlacePhoto } from '../ui/common'
import { Page, useTitle } from '../ui/Shell'
import { openPlace } from '../ui/PlaceSheet'

// Places and themes this account opened lately (from its own usage events, newest first).
export function Recent() {
  useTitle('Đã xem gần đây')
  const recent = useUi((u) => u.recent).filter((r) => (r.kind === 'theme' ? themeOf(r.id) : info(r.id)))
  useWarm(recent.filter((r) => r.kind !== 'theme').map((r) => r.id))
  const when = (iso: string) => new Date(iso).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'numeric' })
  return (
    <Page>
      <header className="tg-head"><div><p className="tg-kicker">Thư viện của bạn</p><h1>Đã xem gần đây</h1><p>Nơi và chủ đề bạn mở gần đây, theo tài khoản.</p></div></header>
      {recent.length === 0 ? <Empty art={<ArtCup />} title="Chưa xem gì gần đây" body="Mở một chủ đề hoặc xem chi tiết một nơi, nó sẽ hiện ở đây." action={<button type="button" className="tg-btn tg-btn--primary" onClick={() => go('/')}>Về Dành cho bạn</button>} /> : (
        <ul className="tg-recent">
          {recent.map((r) => {
            const t = r.kind === 'theme' ? themeOf(r.id) : null
            const p = t ? null : info(r.id)
            return (
              <li key={`${r.kind}:${r.id}`}>
                <button type="button" onClick={(e) => (t ? openTheme(r.id) : openPlace(r.id, e.currentTarget.querySelector('img')))}>
                  {t ? <img src={t.photo} alt="" /> : <PlacePhoto id={r.id} />}
                  <span><b>{t ? t.short : p?.name}</b><small>{t ? `Chủ đề · ${t.category}` : [p?.category, p?.area].filter(Boolean).join(' · ')}</small><time dateTime={r.at}>{when(r.at)}</time></span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Page>
  )
}

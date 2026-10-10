import { useEffect, useRef, useState } from 'react'
import { acceptTerms, signInHref, signOut, startGuest, useAccount } from '../account'
import { navigate } from '../../router'
import { Icon, Logo } from '../ui/icons'
import { useTitle } from '../ui/Shell'

const ERRORS: Record<string, string> = {
  denied: 'Bạn chưa cho phép Google chia sẻ tài khoản, nên mình chưa đăng nhập được.',
  state: 'Phiên đăng nhập đã hết hạn. Bấm lại nút bên dưới nhé.',
  failed: 'Google chưa xác nhận được tài khoản. Thử lại sau ít phút nhé.',
}

// /app needs an account (docs/WEB.md §1): Google sign-in, then a one-time consent to the terms
// and the data policy. `next` is where Google sends the browser back.
export function Auth({ next }: { next: string }) {
  const account = useAccount()
  useTitle(account?.needs_consent ? 'Điều khoản' : 'Đăng nhập')
  const error = new URLSearchParams(location.search).get('error')
  const [trying, setTrying] = useState(false)
  const [tryErr, setTryErr] = useState(false)
  const guest = () => { setTrying(true); setTryErr(false); startGuest().catch(() => { setTryErr(true); setTrying(false) }) }
  return (
    <div className="tg-auth">
      <aside className="tg-auth__art" aria-hidden="true"><div className="tg-auth__img" /><a className="tg-auth__logo" href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}><Logo size={34} dark /><span>TripGuardian</span></a><p>Đà Lạt có cả nghìn chỗ đẹp.<br /><em>Chuyến này của bạn cần mấy chỗ?</em></p></aside>
      <main className="tg-auth__main">
        <div className="tg-auth__card tg-stage" key={account ? 'consent' : 'pick'}>
          {account?.needs_consent ? <Consent version={account.terms_version} /> : (
            <>
              <h1>Bắt đầu chuyến Đà Lạt</h1><p className="tg-muted">Nói một câu, TripGuardian dựng cả chuyến. Mỗi gợi ý có lý do và có cái giá.</p>
              {error && ERRORS[error] && <p className="tg-auth__err" role="alert">{ERRORS[error]}</p>}
              <a className="tg-btn tg-btn--primary tg-auth__try" href={signInHref(next)}>Tiếp tục với Google <Icon name="arrow" size={18} /></a>
              <button type="button" className="tg-btn tg-btn--soft tg-auth__try" disabled={trying} onClick={guest}>Dùng thử, không cần đăng nhập</button>
              {tryErr && <p className="tg-auth__err" role="alert">Chưa mở được bản dùng thử, bạn thử lại nhé.</p>}
              <p className="tg-faint tg-auth__fine">Dùng thử được 1 chuyến trong ngày và không lưu lịch sử. Đăng nhập để giữ chuyến của bạn.</p>
              <p className="tg-faint tg-auth__fine"><Icon name="shield" size={14} /> Chuyến đi, hồ sơ và lịch sử của bạn được lưu theo tài khoản, mở được trên mọi máy. Bạn xóa tài khoản lúc nào cũng được.</p>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function Consent({ version }: { version: string }) {
  const [ok, setOk] = useState(false)
  const [learn, setLearn] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(false)
  const [doc, setDoc] = useState<'terms' | 'data' | null>(null)
  const agree = () => {
    setBusy(true)
    acceptTerms(version, learn).catch(() => { setErr(true); setBusy(false) })
  }
  return (
    <>
      <h1>Trước khi bắt đầu</h1>
      <p className="tg-muted">Đọc nhanh cách TripGuardian dùng dữ liệu của bạn:</p>
      <ul className="tg-auth__terms">
        <li>Tên, email và ảnh từ Google dùng để đăng nhập và hiện trên hồ sơ.</li>
        <li>Chuyến đi, lời bạn nhắn và các thao tác trong app được lưu để giữ chuyến cho bạn và để đội ngũ cải thiện gợi ý. Người quản trị xem được các dữ liệu này.</li>
        <li>Hồ sơ và những lựa chọn bạn lặp lại qua nhiều chuyến (cách tới, phương tiện, ngân sách, giờ nhận phòng, gu đi chơi) chỉ là gợi ý ban đầu; chuyến hiện tại luôn thắng.</li>
        <li>Không thu vị trí GPS. Google Calendar chỉ được ghi khi bạn bấm xác nhận.</li>
        <li>Xóa tài khoản trong Hồ sơ: dữ liệu cá nhân bị xóa, số liệu còn lại không gắn với bạn nữa.</li>
      </ul>
      <label className="tg-auth__check"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> <span>Tôi đồng ý với <button type="button" className="tg-link" onClick={(e) => { e.preventDefault(); setDoc('terms') }}>Điều khoản sử dụng</button> và <button type="button" className="tg-link" onClick={(e) => { e.preventDefault(); setDoc('data') }}>Chính sách dữ liệu</button> (bản {version}).</span></label>
      <label className="tg-auth__check"><input type="checkbox" checked={learn} onChange={(e) => setLearn(e.target.checked)} /> <span>Nhớ lựa chọn của tôi qua các chuyến để lần sau hỏi ít hơn (tùy chọn, tắt được trong Hồ sơ).</span></label>
      {doc && <Legal doc={doc} version={version} onClose={() => setDoc(null)} />}
      {err && <p className="tg-auth__err" role="alert">Chưa lưu được, thử lại nhé.</p>}
      <button type="button" className="tg-btn tg-btn--primary" disabled={!ok || busy} onClick={agree}>Bắt đầu <Icon name="arrow" size={18} /></button>
      <p className="tg-auth__foot"><button type="button" className="tg-link tg-link--quiet" onClick={() => void signOut()}>Dùng tài khoản khác</button></p>
    </>
  )
}

// The two texts behind the consent box, short and in plain words (what is stored: docs/ACCOUNTS.md).
const LEGAL = {
  terms: ['Điều khoản sử dụng', [
    'TripGuardian là công cụ miễn phí giúp bạn lên lịch đi Đà Lạt, hiện đang trong giai đoạn thử nghiệm.',
    'Gợi ý dựa trên dữ liệu công khai (đánh giá Google Maps, clip TikTok) nên có thể thiếu hoặc cũ. Giờ mở cửa, giá và thời gian di chuyển là ước tính: bạn kiểm tra lại trước khi đi, nhất là nơi cần đặt trước.',
    'TripGuardian không đặt chỗ, không bán vé và không nhận thanh toán. Giữ hay bỏ một nơi luôn là quyết định của bạn.',
    'Bạn đăng nhập bằng tài khoản Google của chính mình và không dùng TripGuardian để gây hại cho hệ thống hay người khác.',
    'Tính năng có thể thay đổi hoặc tạm dừng. Khi điều khoản đổi, TripGuardian hỏi bạn đồng ý lại trước khi dùng tiếp.',
  ]],
  data: ['Chính sách dữ liệu', [
    'Lưu gì: tên, email và ảnh từ tài khoản Google; hồ sơ bạn tự nhập (thành phố, phương tiện, hay đi với ai, ảnh đại diện); chuyến đi, lời bạn nhắn với TripGuardian, các nơi bạn chọn hay bỏ, lần bấm “Đã đến”, đánh giá và góp ý; số liệu sử dụng như màn đã mở và nút đã bấm.',
    'Dùng để: giữ chuyến cho bạn trên mọi máy, gợi ý hợp gu hơn, và để đội ngũ cải thiện sản phẩm. Người quản trị TripGuardian xem được các dữ liệu này.',
    'Không thu: vị trí GPS và các lịch Google khác của bạn. Google Calendar chỉ được ghi vào một lịch riêng do TripGuardian tạo, và chỉ khi bạn bấm xác nhận.',
    'Nhớ lựa chọn: nếu bạn bật, TripGuardian ghi lại những lựa chọn bạn tự chọn hoặc tự nói trong mỗi chuyến (không ghi điều chỉ được gợi ý sẵn) để các chuyến sau hỏi ít hơn. Một lựa chọn chỉ thành gợi ý khi bạn chọn giống nhau nhiều lần; gợi ý hiện trên vé chuyến và sửa được. Tắt trong Hồ sơ thì phần đã nhớ bị xóa.',
    'Điều bạn kể về sức khỏe hay thể chất chỉ dùng trong chuyến đang lập, không lưu lâu dài. Thông báo chỉ gửi khi bạn bật, tắt từng loại trong Hồ sơ.',
    'Bảo vệ: phiên đăng nhập chỉ lưu ở dạng băm; quyền ghi Google Calendar được mã hóa.',
    'Xóa: Hồ sơ → Xóa tài khoản xóa hồ sơ, ảnh, liên kết Google Calendar, thông báo và phiên đăng nhập. Chuyến đi, góp ý và số liệu sử dụng còn lại để thống kê nhưng không còn gắn với bạn.',
  ]],
} as const

function Legal({ doc, version, onClose }: { doc: 'terms' | 'data'; version: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  const [title, items] = LEGAL[doc]
  return (
    <dialog ref={ref} className="tg-legal" aria-labelledby="tg-legal-h" onClose={onClose} onClick={(e) => { if (e.target === ref.current) ref.current?.close() }}>
      <header><h2 id="tg-legal-h">{title}</h2><button type="button" className="tg-iconbtn" aria-label="Đóng" onClick={() => ref.current?.close()}><Icon name="x" size={18} /></button></header>
      <p className="tg-faint">Bản {version}</p>
      <ul>{items.map((t) => <li key={t}>{t}</li>)}</ul>
      <button type="button" className="tg-btn tg-btn--primary tg-btn--sm" onClick={() => ref.current?.close()}>Đã đọc</button>
    </dialog>
  )
}

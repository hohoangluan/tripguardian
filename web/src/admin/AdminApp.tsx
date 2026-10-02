import gsap from 'gsap'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSnapshot } from '../data/store'
import { match, navigate, usePath } from '../router'
import { Icon } from '../ui/bits'
import { useDecisions } from './decisions'
import { Analytics } from './screens/Analytics'
import { Dashboard } from './screens/Dashboard'
import { Evidence } from './screens/Evidence'
import { Labels } from './screens/Labels'
import { Places } from './screens/Places'
import { Review } from './screens/Review'
import { Sessions } from './screens/Sessions'
import { System } from './screens/System'
import './admin.css'

const NAV = [
  { path: '/admin', label: 'Tổng quan', icon: 'gauge', key: 'd', group: 'Công việc' },
  { path: '/admin/review', label: 'Hàng đợi duyệt', icon: 'inbox', key: 'r', group: 'Công việc' },
  { path: '/admin/labels', label: 'Gán nhãn', icon: 'check', key: 'l', group: 'Công việc' },
  { path: '/admin/places', label: 'Địa điểm', icon: 'pin', key: 'p', group: 'Dữ liệu' },
  { path: '/admin/evidence', label: 'Bằng chứng', icon: 'layers', key: 'e', group: 'Dữ liệu' },
  { path: '/admin/sessions', label: 'Phiên chuyến đi', icon: 'route', key: 's', group: 'Vận hành' },
  { path: '/admin/analytics', label: 'Phân tích', icon: 'chart', key: 'a', group: 'Vận hành' },
  { path: '/admin/system', label: 'Hệ thống', icon: 'server', key: 'm', group: 'Vận hành' },
]
const GROUPS = [...new Set(NAV.map((n) => n.group))]

type Theme = 'light' | 'dark'
const THEME_KEY = 'tg.admin.theme'

// Follows the system until the reviewer picks one; the pick is a per-browser convenience.
function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem(THEME_KEY)
      if (saved === 'light' || saved === 'dark') return saved
    } catch {
      /* storage blocked: fall back to the system theme */
    }
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  const toggle = () =>
    setTheme((t) => {
      const next = t === 'dark' ? 'light' : 'dark'
      try {
        localStorage.setItem(THEME_KEY, next)
      } catch {
        /* applied, just not remembered */
      }
      return next
    })
  return [theme, toggle] as const
}

export default function AdminApp() {
  const path = usePath()
  const { snap, error } = useSnapshot()
  const decisions = useDecisions()
  const [palette, setPalette] = useState(false)
  const [help, setHelp] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const main = useRef<HTMLDivElement>(null)
  const base = '/' + path.split('?')[0].split('/').filter(Boolean).slice(0, 2).join('/')
  const pending = snap ? snap.review.filter((r) => !decisions[r.id]).length : 0

  useEffect(() => {
    document.title = 'TripGuardian Admin'
    let g = false
    let t: ReturnType<typeof setTimeout>
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest('input, textarea, select')
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette((p) => !p)
        return
      }
      if (typing) return
      if (e.key === '?') setHelp((h) => !h)
      if (e.key === 'Escape') (setHelp(false), setPalette(false))
      if (g) {
        const n = NAV.find((x) => x.key === e.key)
        if (n) navigate(n.path)
        g = false
        return
      }
      if (e.key === 'g') {
        g = true
        clearTimeout(t)
        t = setTimeout(() => (g = false), 900)
      }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  // Screens slide in on a shallow 3D plane: fast enough not to slow a reviewer down.
  useLayoutEffect(() => {
    if (!main.current || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    gsap.fromTo(main.current, { opacity: 0, rotateX: 4, y: 14 }, { opacity: 1, rotateX: 0, y: 0, duration: 0.35, ease: 'power2.out', clearProps: 'transform' })
  }, [base])

  let screen
  let m: Record<string, string> | null
  if (!snap) screen = <p className="a-empty">{error ? `Không tải được snapshot: ${error}` : 'Đang tải snapshot'}</p>
  else if (base === '/admin') screen = <Dashboard snap={snap} />
  else if (base === '/admin/review') screen = <Review snap={snap} />
  else if (base === '/admin/labels') screen = <Labels />
  else if ((m = match(path, '/admin/places/:id'))) screen = <Places snap={snap} openId={m.id} />
  else if (base === '/admin/places') screen = <Places snap={snap} />
  else if (base === '/admin/evidence') screen = <Evidence snap={snap} />
  else if (base === '/admin/sessions') screen = <Sessions />
  else if (base === '/admin/analytics') screen = <Analytics />
  else if (base === '/admin/system') screen = <System snap={snap} />
  else screen = <p className="a-empty">Không có trang này.</p>

  return (
    <div className="admin" data-theme={theme}>
      <aside className="a-side">
        <a
          className="a-brand"
          href="/admin"
          onClick={(e) => {
            e.preventDefault()
            navigate('/admin')
          }}
        >
          <Emblem />
          <span>
            TripGuardian <small>Admin · Đà Lạt</small>
          </span>
        </a>
        <button className="a-find" onClick={() => setPalette(true)}>
          <Icon name="search" size={15} /> <span>Tìm nhanh</span> <kbd>Ctrl K</kbd>
        </button>
        <nav aria-label="Admin">
          {GROUPS.map((g) => (
            <div className="a-nav" key={g}>
              <p className="a-nav__group">{g}</p>
              {NAV.filter((n) => n.group === g).map((n) => (
                <button key={n.path} className={base === n.path || (n.path !== '/admin' && base.startsWith(n.path)) ? 'is-on' : ''} onClick={() => navigate(n.path)}>
                  <Icon name={n.icon} size={17} />
                  <span>{n.label}</span>
                  {n.path === '/admin/review' && pending > 0 && <b className="a-badge">{pending}</b>}
                  <kbd>g {n.key}</kbd>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="a-side__foot">
          <button onClick={() => setHelp(true)}>
            <Icon name="keyboard" size={15} /> Phím tắt <kbd>?</kbd>
          </button>
          <button onClick={toggleTheme}>
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={15} /> {theme === 'dark' ? 'Nền sáng' : 'Nền tối'}
          </button>
          {snap && <small>Snapshot {new Date(snap.build.at).toLocaleString('vi-VN')}</small>}
        </div>
      </aside>
      <div className="a-main" ref={main}>
        {screen}
      </div>
      {palette && snap && <Palette snap={snap} onClose={() => setPalette(false)} />}
      {help && <Help onClose={() => setHelp(false)} />}
    </div>
  )
}

function Emblem() {
  return (
    <svg className="a-emblem" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 2l12 14-12 14L4 16z" fill="none" stroke="#f2b31b" strokeWidth="1.6" />
      <path d="M16 8l5 7h-3l4 5h-4l3 4H11l3-4h-4l4-5h-3z" fill="#d5dee0" />
    </svg>
  )
}

function Palette({ snap, onClose }: { snap: NonNullable<ReturnType<typeof useSnapshot>['snap']>; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const results = useMemo(() => {
    const f = q.trim().toLowerCase()
    const pages = NAV.filter((n) => n.label.toLowerCase().includes(f)).map((n) => ({ label: n.label, hint: 'Trang', go: n.path }))
    const places = f.length < 2 ? [] : snap.places.filter((p) => p.name.toLowerCase().includes(f)).slice(0, 8).map((p) => ({ label: p.name, hint: p.kind === 'experience' ? 'Địa điểm có bằng chứng' : 'Địa điểm Google', go: `/admin/places/${encodeURIComponent(p.id)}` }))
    return [...pages, ...places]
  }, [q, snap])
  const go = (to: string) => (navigate(to), onClose())
  return (
    <div className="a-modal" role="dialog" aria-modal="true" aria-label="Tìm nhanh" onClick={onClose}>
      <div className="a-palette" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={q}
          onChange={(e) => (setQ(e.target.value), setI(0))}
          placeholder="Tìm trang hoặc địa điểm"
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') (e.preventDefault(), setI((x) => Math.min(results.length - 1, x + 1)))
            if (e.key === 'ArrowUp') (e.preventDefault(), setI((x) => Math.max(0, x - 1)))
            if (e.key === 'Enter' && results[i]) go(results[i].go)
            if (e.key === 'Escape') onClose()
          }}
        />
        <ul>
          {results.map((r, j) => (
            <li key={r.go}>
              <button className={j === i ? 'is-on' : ''} onMouseEnter={() => setI(j)} onClick={() => go(r.go)}>
                <span>{r.label}</span>
                <small>{r.hint}</small>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function Help({ onClose }: { onClose: () => void }) {
  const rows = [
    ['g rồi d / r / l / p / e / s / a / m', 'Đi tới trang'],
    ['Ctrl K', 'Tìm nhanh'],
    ['j / k', 'Mục kế / mục trước (hàng đợi duyệt)'],
    ['a', 'Chấp nhận'],
    ['d', 'Vô hiệu'],
    ['r rồi 1–5', 'Báo lỗi theo loại'],
    ['x', 'Chọn mục để xử lý hàng loạt'],
    ['Shift A', 'Chấp nhận các mục đã chọn'],
    ['u', 'Hoàn tác mục đang xem'],
    ['c / w / u / s', 'Gán nhãn: đúng / sai / không chắc / bỏ qua (trang Gán nhãn)'],
  ]
  return (
    <div className="a-modal" role="dialog" aria-modal="true" aria-label="Phím tắt" onClick={onClose}>
      <div className="a-help" onClick={(e) => e.stopPropagation()}>
        <h2>Phím tắt</h2>
        <table>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th>
                  <kbd>{k}</kbd>
                </th>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

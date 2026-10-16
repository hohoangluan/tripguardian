import { Icon } from './icons'

// Numbered pages under a grid of Lựa chọn (a place tab, the lodging tab): first, last and the pages around the current
// one, ellipses between. page is 0-based, the buttons 1-based; from / to are ranks of the cards on screen.
export function Pager({ label, total, page, pages, from, to, busy, onPage }: { label: string; total: number; page: number; pages: number; from: number; to: number; busy: boolean; onPage: (n: number) => void }) {
  const cur = page + 1
  const nums = [...new Set([1, cur - 2, cur - 1, cur, cur + 1, cur + 2, pages])].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b)
  return (
    <nav className="tg-pager" aria-label={`Trang của nhóm ${label}`} aria-busy={busy}>
      <span className="tg-pager__info tg-faint">Nơi {from}–{to} trong {total}, xếp từ hợp nhất</span>
      {pages > 1 && (
        <div className="tg-pager__pages">
          <button type="button" className="tg-pager__btn" disabled={busy || cur === 1} onClick={() => onPage(cur - 1)} aria-label="Trang trước"><Icon name="chevronLeft" size={18} /></button>
          {nums.flatMap((n, k) => [
            ...(k > 0 && n - nums[k - 1] > 1 ? [<span key={`gap${n}`} className="tg-pager__gap" aria-hidden="true">…</span>] : []),
            <button key={n} type="button" className="tg-pager__btn" aria-current={n === cur ? 'page' : undefined} disabled={busy} onClick={() => n !== cur && onPage(n)}>{n}</button>,
          ])}
          <button type="button" className="tg-pager__btn" disabled={busy || cur === pages} onClick={() => onPage(cur + 1)} aria-label="Trang sau"><Icon name="chevronRight" size={18} /></button>
        </div>
      )}
    </nav>
  )
}

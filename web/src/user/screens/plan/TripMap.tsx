import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { mapsRouteLink } from '../../../data/store'
import { info } from '../../lib'
import type { DayRoute } from '../../planning/types'
import { Icon } from '../../ui/icons'

// Offline map of Đà Lạt (mẫu ui_mock_for_design/designs/itinerary): 5 × 5 OpenStreetMap tiles at zoom 12 in /img/map, drawn on a canvas,
// numbered pins on top. With a day's route (OSRM path from the backend, planning/routes) the map draws that road line and
// lights the leg that ends at the stop in focus; without one it draws a dashed line through the stops in order, which is
// a sketch of the order, not a route.
const Z = { x: 3279, y: 1909, size: 256, n: 4096, cols: 5 }
const SIDE = Z.size * Z.cols

type Pt = { lat: number; lng: number }
const project = (p: Pt): [number, number] => {
  const lat = (p.lat * Math.PI) / 180
  return [((p.lng + 180) / 360 * Z.n - Z.x) * Z.size, ((1 - Math.asinh(Math.tan(lat)) / Math.PI) / 2 * Z.n - Z.y) * Z.size]
}
const inside = ([x, y]: [number, number]) => x >= 0 && y >= 0 && x <= SIDE && y <= SIDE

let mosaic: Promise<HTMLCanvasElement> | null = null
function loadMosaic() {
  mosaic ??= new Promise((resolve) => {
    const c = document.createElement('canvas')
    c.width = c.height = SIDE
    const g = c.getContext('2d')!
    const jobs: Promise<void>[] = []
    for (let x = 0; x < Z.cols; x++) for (let y = 0; y < Z.cols; y++)
      jobs.push(new Promise((done) => {
        const im = new Image()
        im.onload = () => { g.drawImage(im, x * Z.size, y * Z.size); done() }
        im.onerror = () => done()
        im.src = `/img/map/${Z.x + x}-${Z.y + y}.png`
      }))
    void Promise.all(jobs).then(() => resolve(c))
  })
  return mosaic
}

export interface Stop { id: string; n: number }

type Path = NonNullable<DayRoute['route']>

// Index of the path vertex nearest to each stop, never going back: where each leg of the road starts and ends.
function legStarts(path: Path, pts: [number, number][]) {
  const v = path.coords.map(([lat, lng]) => project({ lat, lng }))
  let from = 0
  return { v, at: pts.map(([x, y]) => {
    let best = from
    for (let i = from; i < v.length; i++) if ((v[i][0] - x) ** 2 + (v[i][1] - y) ** 2 < (v[best][0] - x) ** 2 + (v[best][1] - y) ** 2) best = i
    from = best
    return best
  }) }
}

// groups: one list of place ids per line (a day); pins are numbered 1.. through all groups in order.
// routes: the road path of each group (null / missing: sketch). ends: names for the opening and closing point of a single day.
export function TripMap({ groups, title, className = '', hot, onHot, onOpen, labels = true, routes, ends, children }: {
  groups: string[][]; title: string; className?: string; hot?: string | null; onHot?: (id: string | null) => void; onOpen?: (id: string) => void; labels?: boolean
  routes?: (Path | null)[]; ends?: { start: string; end: string }; children?: ReactNode
}) {
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<[number, number]>([0, 0]) // dragged away from the centre of the pins; only means something zoomed in
  const drag = useRef<{ x: number; y: number; pan: [number, number] } | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [tiles, setTiles] = useState<HTMLCanvasElement | null>(null)
  const [size, setSize] = useState<[number, number]>([0, 0])
  useEffect(() => { void loadMosaic().then(setTiles) }, [])
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const read = () => setSize([el.clientWidth, el.clientHeight])
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const [w, h] = size
  let k = 0
  const lines = groups.map((ids) => ids.flatMap((id) => { const p = info(id); return p ? [{ id, n: ++k, xy: project(p) }] : [] }))
  const all = lines.flat()
  const shown = all.filter((s) => inside(s.xy))
  // the road of each line: its vertices, and where each stop sits on it
  const roads = lines.map((line, i) => {
    const path = routes?.[i]
    return path && path.coords.length > 1 ? { path, ...legStarts(path, line.map((s) => s.xy)) } : null
  })
  const single = groups.length === 1 && roads[0] ? roads[0] : null
  const endPts: [number, number][] = single ? [single.v[0], single.v[single.v.length - 1]] : []
  const hotAt = single ? lines[0].findIndex((s) => s.id === hot) : -1
  const out = all.length - shown.length
  // fit the pins with padding; never zoom out past the tiles, never in beyond ~2.2x
  let scale = Math.max(w, h) / SIDE
  let ox = 0
  let oy = 0
  if (w && h) {
    const pts = (shown.length ? shown : [{ xy: [SIDE / 2, SIDE / 2] as [number, number] }]).map((s) => s.xy).concat(endPts.filter(inside))
    const xs = pts.map((p) => p[0])
    const ys = pts.map((p) => p[1])
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const fit = Math.min((w - 120) / Math.max(40, x1 - x0), (h - 150) / Math.max(40, y1 - y0))
    scale = Math.min(4, Math.max(Math.max(w, h) / SIDE, Math.min(2.2, fit)) * zoom)
    ox = Math.min(0, Math.max(w - SIDE * scale, w / 2 - ((x0 + x1) / 2) * scale + pan[0]))
    oy = Math.min(0, Math.max(h - SIDE * scale, h / 2 - ((y0 + y1) / 2) * scale + pan[1]))
  }
  const at = (xy: [number, number]) => [ox + xy[0] * scale, oy + xy[1] * scale] as const

  useEffect(() => {
    const c = canvas.current
    if (!c || !w || !h) return
    const dpr = window.devicePixelRatio || 1
    c.width = w * dpr
    c.height = h * dpr
    const g = c.getContext('2d')!
    g.scale(dpr, dpr)
    g.fillStyle = '#ececec'
    g.fillRect(0, 0, w, h)
    if (tiles) { g.globalAlpha = 0.86; g.drawImage(tiles, ox, oy, SIDE * scale, SIDE * scale); g.globalAlpha = 1 }
    const css = getComputedStyle(c)
    const ink = css.getPropertyValue('--tg-pine').trim() || '#111111'
    const brand = css.getPropertyValue('--tg-brand').trim() || ink
    g.lineCap = 'round'
    g.lineJoin = 'round'
    const trace = (pts: readonly (readonly [number, number])[]) => { g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke() }
    lines.forEach((line, li) => {
      const road = roads[li]
      if (road) {
        const pts = road.v.map(at)
        const leg = li === 0 && hotAt >= 0 ? [hotAt > 0 ? road.at[hotAt - 1] : 0, road.at[hotAt]] : null
        g.setLineDash([])
        g.strokeStyle = '#fff'; g.lineWidth = leg ? 7 : 8; trace(pts)
        g.strokeStyle = brand; g.lineWidth = leg ? 4 : 5; g.globalAlpha = leg ? 0.42 : 1; trace(pts); g.globalAlpha = 1
        if (leg && leg[1] > leg[0]) {
          const part = pts.slice(leg[0], leg[1] + 1)
          g.strokeStyle = '#fff'; g.lineWidth = 11; trace(part)
          g.strokeStyle = brand; g.lineWidth = 7; trace(part)
        }
        return
      }
      const pts = line.filter((s) => inside(s.xy)).map((s) => at(s.xy))
      if (pts.length < 2) return
      g.strokeStyle = ink
      g.lineWidth = 2.5
      g.setLineDash([5, 6])
      trace(pts)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tiles, w, h, zoom, pan, hotAt, routes, groups.map((g) => g.join(',')).join('|')])

  return (
    <div className={`tg-it-map ${zoom > 1 ? 'is-pannable' : ''} ${className}`} ref={box} role="group" aria-label={title}
      onPointerDown={(e) => { if (zoom > 1 && !(e.target as HTMLElement).closest('button, a')) { drag.current = { x: e.clientX, y: e.clientY, pan }; e.currentTarget.setPointerCapture(e.pointerId) } }}
      onPointerMove={(e) => { const d = drag.current; if (d) setPan([d.pan[0] + e.clientX - d.x, d.pan[1] + e.clientY - d.y]) }}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}>
      <canvas ref={canvas} aria-hidden="true" />
      <div className="tg-it-pins">
        {shown.map((s) => {
          const [x, y] = at(s.xy)
          const on = hot === s.id
          return (
            <span key={`${s.id}-${s.n}`}>
              <button type="button" className={`tg-it-pin ${on ? 'is-hot' : ''}`} style={{ left: x, top: y }} aria-label={`${s.n}. ${info(s.id)?.name ?? s.id}`}
                onMouseEnter={() => onHot?.(s.id)} onMouseLeave={() => onHot?.(null)} onFocus={() => onHot?.(s.id)} onBlur={() => onHot?.(null)} onClick={() => onOpen?.(s.id)}>{s.n}</button>
              {labels && on && <span className="tg-it-pin__label" style={{ left: Math.max(70, Math.min(w - 70, x)), top: y }}>{info(s.id)?.name}</span>}
            </span>
          )
        })}
      </div>
      {single && ends && (
        <div className="tg-it-pins">
          {([['start', endPts[0], ends.start, 'Xuất phát'], ['end', endPts[1], ends.end, 'Kết thúc ngày']] as const).map(([k, xy, name, tag]) => {
            const [x, y] = at(xy)
            if (!inside(xy)) return null
            return (
              <span key={k}>
                <span className={`tg-it-end is-${k}`} style={{ left: x, top: y }} aria-hidden="true" />
                <span className="tg-it-callout" style={{ left: Math.max(90, Math.min(w - 90, x)), top: y }}><small>{tag}</small><b>{name}</b></span>
              </span>
            )
          })}
        </div>
      )}
      <div className="tg-it-zoom" role="group" aria-label="Thu phóng bản đồ">
        <button type="button" aria-label="Phóng to" disabled={zoom >= 3} onClick={() => setZoom((z) => Math.min(3, +(z * 1.4).toFixed(2)))}><Icon name="plus" size={18} /></button>
        <button type="button" aria-label="Thu nhỏ" disabled={zoom <= 1} onClick={() => { const z = Math.max(1, +(zoom / 1.4).toFixed(2)); setZoom(z); if (z === 1) setPan([0, 0]) }}><Icon name="minus" size={18} /></button>
      </div>
      {out > 0 && <span className="tg-it-map__out">{out} nơi nằm ngoài khu vực bản đồ</span>}
      <span className="tg-it-map__credit">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a></span>
      {children}
    </div>
  )
}

export function MapsLink({ ids }: { ids: string[] }) {
  const stops = ids.map((id) => info(id)).filter((p): p is NonNullable<typeof p> => !!p)
  if (stops.length < 2) return null
  return <a className="tg-it-chip" href={mapsRouteLink(stops)} target="_blank" rel="noreferrer">Google Maps <Icon name="external" size={13} /></a>
}

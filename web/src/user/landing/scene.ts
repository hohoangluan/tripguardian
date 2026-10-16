import * as THREE from 'three'
import { GRID, inBounds, toXZ, WORLD } from './geo'
import { Mascot, type MascotAct } from './mascot'
import { decodeLandscape, landscape, setLandscape } from './terrain'

// The landing's scene (docs/UI_SPEC_LANDING.md §2): a living journey map of Đà Lạt with the TripGuardian cloud
// (mascot.ts) flying in front of it. The map lies flat and stays quiet: paper tinted by the real land cover and
// relief, contour lines, the real lakes and main roads, a faint graticule, a golden dot for every place, and the
// example day as a terracotta dotted route with photo postcards. The camera glides over it from station to station;
// the cloud is always big, near the camera, and is the one thing that moves a lot. The paper takes the colour of the
// hour (dawn, noon, sunset). Plain three.js, driven from outside: the page scrubs `SceneState` with GSAP; the scene only
// eases toward it and draws. The visitor can drag to turn the view, or explore freely.

export interface ScenePlace { name: string; lat: number; lng: number; photo?: string }
export interface SceneState {
  cam: number // camera keyframe, 0..5 (hero, understand, choose, evidence, itinerary, feedback)
  dots: number // 1 = every place lit, 0 = only the chosen ones
  five: number // 0..1 the postcards rising
  route: number // 0..1 drawn share of the route
  travel: number // 0..1 where the day has got to along the route; the itinerary camera follows it
  areas: number // 0..1 area labels
  shift: number // horizontal framing: share of the width kept free for text on the left
  hour: number // 0..1 the example day's clock: dawn, noon, sunset (the paper's light)
  stamp: number // 0..1 the last station: the cloud stamps its map (to 0.6), then waves
  lift: number // 0..1 leaving for the app: the camera rises into the golden haze
}

const PAPER = '#f6efe2'
const C = { sun: '#f4b43c', ink3: '#8a8072' }

// The light of the day at three moments (hour 0, 0.5, 1): the tint over the whole map (multiplied into the paper),
// the sky and haze where the map fades out, and the light on the cloud.
type Moment = { tint: string; top: string; low: string; sun: string; sunI: number; sunAt: [number, number, number]; hemi: [string, string] }
const DAYLIGHT: Moment[] = [
  { tint: '#fff1e1', top: '#efe6da', low: '#f7dfbd', sun: '#ffe2bf', sunI: 2.2, sunAt: [140, 60, -110], hemi: ['#fff2e2', '#d9c7ae'] },
  { tint: '#ffffff', top: '#dde8ee', low: '#f4eee4', sun: '#fff6e8', sunI: 2.4, sunAt: [40, 220, 60], hemi: ['#ffffff', '#d4cfc4'] },
  { tint: '#ffe1c9', top: '#e8cbb4', low: '#efb48a', sun: '#ff9a5c', sunI: 2.1, sunAt: [-150, 55, 40], hemi: ['#ffe3cf', '#c6ad98'] },
]

// Camera keyframes as an orbit around a point on the map: distance, pitch above the map, yaw (0 = from the south,
// looking north; north is -z). The itinerary key follows the route; the evidence key frames the focus postcard.
type Key = { look: THREE.Vector3; dist: number; pitch: number; yaw: number }
const xz = (lat: number, lng: number, y = 0) => { const [x, z] = toXZ(lat, lng); return new THREE.Vector3(x, y, z) }

const STEM = 4.5
const CARD = { w: 6.2, h: 7.4 }
const MAP_Y = { cover: 0, contour: 0.03, lake: 0.05, road: 0.07, route: 0.12, dot: 0.3 }

// The cloud's place in front of the camera at each beat (camera space; the view is shifted right by `shift`, so
// x = 0 is already right of the text column), its size, and how far it drifts around that place, like a fish. From
// the evidence beat on it keeps below the middle of the view, where the postcard being talked about stands.
const PERCH: { at: [number, number, number]; size: number; drift: number }[] = [
  { at: [1.2, -0.35, -11], size: 1.7, drift: 1 }, // hero: floating, map open, eyes on the pointer
  { at: [0.6, 0.1, -11], size: 1.6, drift: 0.8 }, // understand: headset on, "…"
  { at: [0.8, -1.0, -12], size: 1.5, drift: 0.7 }, // choose: holds the map up while the postcards rise
  { at: [-1.0, -1.9, -11], size: 1.35, drift: 0.4 }, // evidence: below the postcard that speaks, turned to it
  { at: [1.2, -1.55, -11], size: 1.45, drift: 0.4 }, // itinerary: flies ahead along the route, below the stop in view
  { at: [0.5, -1.55, -11], size: 1.65, drift: 0.5 }, // feedback: below the last stop, stamps the map, waves
]
const PERCH_FREE = { at: [1.9, -1.2, -12] as [number, number, number], size: 1.4 }

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const smooth = (f: number) => f * f * (3 - 2 * f)

function radialTexture(stops: [number, string][]) {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')!
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  stops.forEach(([o, col]) => grad.addColorStop(o, col))
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

// a postcard: the place's real photo in a white border with a soft shadow
function postcard(img: HTMLImageElement | null, brand: string) {
  const W = 248, H = 296, B = 12, R = 14
  const c = document.createElement('canvas')
  c.width = W + 24
  c.height = H + 24
  const g = c.getContext('2d')!
  g.translate(12, 8)
  g.shadowColor = 'rgba(70,48,28,0.28)'
  g.shadowBlur = 14
  g.shadowOffsetY = 6
  g.fillStyle = '#ffffff'
  g.beginPath()
  g.roundRect(0, 0, W, H, R)
  g.fill()
  g.shadowColor = 'transparent'
  const iw = W - B * 2, ih = H - B * 2 - 28
  g.save()
  g.beginPath()
  g.roundRect(B, B, iw, ih, 8)
  g.clip()
  if (img && img.naturalWidth) {
    const s = Math.max(iw / img.naturalWidth, ih / img.naturalHeight)
    const dw = img.naturalWidth * s, dh = img.naturalHeight * s
    g.drawImage(img, B + (iw - dw) / 2, B + (ih - dh) / 2, dw, dh)
  } else {
    const grad = g.createLinearGradient(0, B, 0, B + ih)
    grad.addColorStop(0, PAPER)
    grad.addColorStop(1, '#e4d4ba')
    g.fillStyle = grad
    g.fillRect(B, B, iw, ih)
  }
  g.restore()
  // two short ruled lines where a postcard's message would go, and a stamp dot
  g.fillStyle = '#ece6dc'
  g.fillRect(B, H - 26, iw * 0.55, 3)
  g.fillRect(B, H - 17, iw * 0.35, 3)
  g.fillStyle = brand
  g.beginPath()
  g.arc(W - B - 8, H - 18, 6, 0, Math.PI * 2)
  g.fill()
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

// Contour lines over the height grid (marching squares on every `stride`-th vertex), as pairs of points on the map;
// `major` collects every fifth level apart.
function contours(stride: number, step: number) {
  const L = landscape()
  const { cols, rows, height } = L
  const minor: number[] = [], major: number[] = []
  const nx = Math.floor((cols - 1) / stride), nz = Math.floor((rows - 1) / stride)
  const at = (ix: number, iz: number) => height[iz * stride * cols + ix * stride]
  const X = (ix: number) => ((ix * stride) / GRID.nx) * WORLD.w - WORLD.w / 2
  const Z = (iz: number) => ((iz * stride) / GRID.nz) * WORLD.d - WORLD.d / 2
  let lo = Infinity, hi = -Infinity
  for (let i = 0; i < height.length; i += stride) { lo = Math.min(lo, height[i]); hi = Math.max(hi, height[i]) }
  for (let k = Math.ceil(lo / step); k * step <= hi; k++) {
    const v = k * step, out = k % 5 === 0 ? major : minor
    for (let iz = 0; iz < nz; iz++)
      for (let ix = 0; ix < nx; ix++) {
        const a = at(ix, iz), b = at(ix + 1, iz), c = at(ix + 1, iz + 1), d = at(ix, iz + 1)
        const idx = (a > v ? 1 : 0) | (b > v ? 2 : 0) | (c > v ? 4 : 0) | (d > v ? 8 : 0)
        if (idx === 0 || idx === 15) continue
        // crossing points on the four edges: top (a-b), right (b-c), bottom (d-c), left (a-d)
        const e = [
          () => [lerp(X(ix), X(ix + 1), (v - a) / (b - a)), Z(iz)],
          () => [X(ix + 1), lerp(Z(iz), Z(iz + 1), (v - b) / (c - b))],
          () => [lerp(X(ix), X(ix + 1), (v - d) / (c - d)), Z(iz + 1)],
          () => [X(ix), lerp(Z(iz), Z(iz + 1), (v - a) / (d - a))],
        ]
        const seg = (p: number, q: number) => { const [x0, z0] = e[p](), [x1, z1] = e[q](); out.push(x0, MAP_Y.contour, z0, x1, MAP_Y.contour, z1) }
        switch (idx) {
          case 1: case 14: seg(0, 3); break
          case 2: case 13: seg(0, 1); break
          case 3: case 12: seg(1, 3); break
          case 4: case 11: seg(1, 2); break
          case 6: case 9: seg(0, 2); break
          case 7: case 8: seg(2, 3); break
          case 5: seg(0, 1); seg(2, 3); break
          case 10: seg(0, 3); seg(1, 2); break
        }
      }
  }
  return { minor: new Float32Array(minor), major: new Float32Array(major) }
}

export interface SceneData { points: [number, number][]; five: ScenePlace[]; focus: number; land: ArrayBuffer }

export class DalatScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(38, 1, 1, 2000)
  private state: SceneState = { cam: 0, dots: 1, five: 0, route: 0, travel: 0, areas: 1, shift: 0.2, hour: 0, stamp: 0, lift: 0 }
  private shown: SceneState = { ...this.state }
  private pointer = new THREE.Vector2()
  private pointerShown = new THREE.Vector2()
  private brand: string
  private lightMat!: THREE.PointsMaterial
  private cards: { group: THREE.Group; ring: THREE.Mesh; mat: THREE.SpriteMaterial }[] = []
  private cardTops: THREE.Vector3[] = []
  private dashes!: THREE.InstancedMesh
  private dashCount = 0
  private routeCurve!: THREE.CatmullRomCurve3
  private stopsAt: number[] = []
  private mascot!: Mascot
  private mascotHidden = false
  private focusLook = new THREE.Vector3()
  private tinted: { mat: { color: THREE.Color }; base: THREE.Color }[] = []
  private sky_!: THREE.ShaderMaterial
  private hemi!: THREE.HemisphereLight
  private sunLight!: THREE.DirectionalLight
  private minorLines: THREE.LineSegments | null = null
  private labels: { el: HTMLElement; at: THREE.Vector3; kind: 'five' | 'area'; i: number }[] = []
  private keys!: Key[]
  private prevFrame = 0
  private frames = 0
  private dpr = 1
  private slow = { ema: 16, level: 0, calm: 0 }
  onReady: (() => void) | null = null
  onGiveUp: (() => void) | null = null
  // Free exploration: an orbit camera the visitor drives (target, distance, yaw, pitch); `blend` mixes it over the
  // story's own camera, so entering and leaving fly smoothly.
  private free = {
    on: false, blend: 0,
    t: new THREE.Vector3(), tT: new THREE.Vector3(), d: 100, dT: 100, yaw: 0, yawT: 0, pitch: 0.7, pitchT: 0.7,
  }
  private effFive = 0
  private size = { w: 1, h: 1 }
  private raf = 0
  private running = false
  private start = performance.now()
  private last = 0
  private tmp = new THREE.Vector3()
  private look = new THREE.Vector3()
  private grey = new THREE.Color(C.ink3)
  private c1 = new THREE.Color()
  private tint1 = new THREE.Color()
  private v1 = new THREE.Vector3()
  private v2 = new THREE.Vector3()
  private v3 = new THREE.Vector3()
  private qa = new THREE.Quaternion()
  private qb = new THREE.Quaternion()
  private cardSee: number[] = []
  private yAxis = new THREE.Vector3(0, 1, 0)
  private disposables: { dispose(): void }[] = []
  // the visitor's own turn on top of the scrubbed camera: yaw 360° around the look point, pitch up and down
  private turn = { yaw: 0, yawT: 0, pitch: 0, pitchT: 0, vel: 0, drag: false }

  static create(canvas: HTMLCanvasElement, data: SceneData, still: boolean) {
    try {
      return new DalatScene(canvas, data, still)
    } catch {
      return null // no WebGL: the page keeps its photo fallback
    }
  }

  private constructor(canvas: HTMLCanvasElement, data: SceneData, private still: boolean) {
    this.brand = getComputedStyle(canvas).getPropertyValue('--tg-brand').trim() || '#b4532a'
    setLandscape(decodeLandscape(data.land))
    performance.mark('tg-build:decode')
    // a screen at 2x or more is sharp enough without multisampling, and it costs a lot of fill rate
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: devicePixelRatio < 2, powerPreference: 'high-performance' })
    this.dpr = Math.min(devicePixelRatio, 1.5)
    this.renderer.setPixelRatio(this.dpr)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.NoToneMapping
    this.scene.fog = new THREE.Fog(DAYLIGHT[0].low, 160, 520)
    // each step leaves a performance mark (tg-build:<step>): the load profile in the browser's Performance panel
    const lap = (step: string) => performance.mark(`tg-build:${step}`)
    lap('renderer')
    this.sky(); lap('sky')
    this.light(); lap('light')
    this.paper(); lap('paper')
    this.relief(); lap('relief')
    this.water(); lap('water')
    this.roads(); lap('roads')
    this.graticule(); lap('graticule')
    this.places(data.points); lap('places')
    this.postcards(data.five); lap('postcards')
    this.routeThrough(data.five); lap('route')
    this.keys = this.buildKeys(data.focus)
    this.mascot = new Mascot(this.brand)
    this.scene.add(this.mascot.root)
    lap('mascot')
  }

  private own<T extends { dispose(): void }>(x: T) {
    this.disposables.push(x)
    return x
  }

  // a material whose colour takes the hour's tint
  private tint<T extends THREE.Material & { color: THREE.Color }>(mat: T) {
    this.tinted.push({ mat, base: mat.color.clone() })
    return this.own(mat)
  }

  private buildKeys(focus: number): Key[] {
    const box = new THREE.Box3().setFromPoints(this.cardTops.map((c) => new THREE.Vector3(c.x, 0, c.z)))
    const mid = box.getCenter(new THREE.Vector3())
    const span = Math.max(box.max.x - box.min.x, box.max.z - box.min.z)
    const f = this.cardTops[focus]
    this.focusLook.set(f.x, f.y - CARD.h * 0.5, f.z)
    const end = this.routeCurve.getPointAt(1)
    return [
      { look: xz(11.935, 108.452), dist: 120, pitch: 0.8, yaw: -0.15 }, // hero: the town and its lakes, from the south
      { look: xz(11.942, 108.445), dist: 92, pitch: 0.92, yaw: 0.28 }, // understand: drift round over Hồ Xuân Hương
      { look: mid, dist: span * 1.15 + 40, pitch: 1.1, yaw: 0 }, // choose: high enough for the whole day
      { look: new THREE.Vector3(f.x, f.y - CARD.h * 0.55, f.z), dist: 40, pitch: 0.42, yaw: 0.45 }, // evidence: eye level with the focus postcard
      { look: new THREE.Vector3(), dist: 82, pitch: 0.85, yaw: 0.1 }, // itinerary: follows the day along the route
      { look: end.clone().setY(0), dist: 78, pitch: 0.62, yaw: 0.55 }, // feedback: the last stop at sunset
    ]
  }

  // sky dome for where the map fades out (free exploration, low views): two bands that follow the hour
  private sky() {
    const geo = this.own(new THREE.SphereGeometry(1400, 32, 16))
    this.sky_ = this.own(new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
      uniforms: { top: { value: new THREE.Color(DAYLIGHT[0].top) }, low: { value: new THREE.Color(DAYLIGHT[0].low) } },
      vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'uniform vec3 top; uniform vec3 low; varying vec3 vP; void main(){ gl_FragColor = vec4(mix(low, top, smoothstep(0.0, 0.6, vP.y)), 1.0); }',
    }))
    this.scene.add(new THREE.Mesh(geo, this.sky_))
  }

  // lights for the cloud (the map itself is unlit paper)
  private light() {
    this.hemi = new THREE.HemisphereLight(DAYLIGHT[0].hemi[0], DAYLIGHT[0].hemi[1], 1.5)
    this.sunLight = new THREE.DirectionalLight(DAYLIGHT[0].sun, DAYLIGHT[0].sunI)
    this.sunLight.position.set(...DAYLIGHT[0].sunAt)
    this.scene.add(this.hemi, this.sunLight)
  }

  // The paper: a wide sheet, and over the mapped area the baked land colours (forest, farmland, town, relief bands)
  // washed most of the way into the paper, so they read as a hand-tinted map, not as terrain.
  private paper() {
    const sheet = new THREE.Mesh(this.own(new THREE.PlaneGeometry(WORLD.w * 4, WORLD.d * 4)), this.tint(new THREE.MeshBasicMaterial({ color: PAPER })))
    sheet.rotation.x = -Math.PI / 2
    sheet.position.y = -0.05
    this.scene.add(sheet)
    const L = landscape()
    const { cols, rows } = L
    const pos = new Float32Array(cols * rows * 3)
    for (let iz = 0, i = 0; iz < rows; iz++)
      for (let ix = 0; ix < cols; ix++, i++) pos.set([(ix / GRID.nx) * WORLD.w - WORLD.w / 2, MAP_Y.cover, (iz / GRID.nz) * WORLD.d - WORLD.d / 2], i * 3)
    const paper = new THREE.Color(PAPER), c = new THREE.Color()
    const col = new Float32Array(cols * rows * 3)
    for (let i = 0; i < cols * rows; i++) {
      c.setRGB(L.color[i * 3] / 255, L.color[i * 3 + 1] / 255, L.color[i * 3 + 2] / 255, THREE.SRGBColorSpace).lerp(paper, 0.58)
      col.set([c.r, c.g, c.b], i * 3)
    }
    const idx = new Uint32Array(GRID.nx * GRID.nz * 6)
    for (let iz = 0, k = 0; iz < GRID.nz; iz++)
      for (let ix = 0; ix < GRID.nx; ix++) {
        const a = iz * cols + ix, b = a + 1, cc = a + cols, d = cc + 1
        idx.set([a, cc, b, b, cc, d], k)
        k += 6
      }
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('color', new THREE.BufferAttribute(col, 3))
    g.setIndex(new THREE.BufferAttribute(idx, 1))
    this.scene.add(new THREE.Mesh(g, this.tint(new THREE.MeshBasicMaterial({ vertexColors: true }))))
  }

  // the relief as contour lines: every 100 m faint, every 500 m a little stronger
  private relief() {
    const { minor, major } = contours(2, 1.6)
    const line = (pts: Float32Array, color: string, opacity: number) => {
      const g = this.own(new THREE.BufferGeometry())
      g.setAttribute('position', new THREE.BufferAttribute(pts, 3))
      const l = new THREE.LineSegments(g, this.tint(new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false })))
      this.scene.add(l)
      return l
    }
    this.minorLines = line(minor, '#a38a6a', 0.22)
    line(major, '#8d7254', 0.4)
  }

  // every lake, flat on the map, with a darker shore line (the edges used by only one triangle)
  private water() {
    const L = landscape()
    const pos = L.waterPos.slice()
    for (let i = 1; i < pos.length; i += 3) pos[i] = MAP_Y.lake
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setIndex(new THREE.BufferAttribute(L.waterIdx, 1))
    this.scene.add(new THREE.Mesh(g, this.tint(new THREE.MeshBasicMaterial({ color: '#c6d4dc' }))))
    const seen = new Map<number, number>()
    const ix = L.waterIdx, n = pos.length / 3
    for (let t = 0; t < ix.length; t += 3)
      for (const [a, b] of [[ix[t], ix[t + 1]], [ix[t + 1], ix[t + 2]], [ix[t + 2], ix[t]]]) {
        const k = Math.min(a, b) * n + Math.max(a, b)
        seen.set(k, (seen.get(k) ?? 0) + 1)
      }
    const shore: number[] = []
    for (const [k, count] of seen) {
      if (count !== 1) continue
      const a = Math.floor(k / n), b = k % n
      shore.push(pos[a * 3], MAP_Y.lake + 0.01, pos[a * 3 + 2], pos[b * 3], MAP_Y.lake + 0.01, pos[b * 3 + 2])
    }
    const sg = this.own(new THREE.BufferGeometry())
    sg.setAttribute('position', new THREE.Float32BufferAttribute(shore, 3))
    this.scene.add(new THREE.LineSegments(sg, this.tint(new THREE.LineBasicMaterial({ color: '#8fa6b4' }))))
  }

  // main roads as white ribbons on a darker casing, from the baked centre lines
  private roads() {
    const L = landscape()
    const ribbon = (extra: number, y: number, color: string) => {
      const points = L.roadXZ.length / 2
      const pos = new Float32Array(points * 6)
      const idx = new Uint32Array((points - L.roadRuns.length) * 6)
      let v = 0, k = 0, start = 0
      L.roadRuns.forEach((run, r) => {
        const w = L.roadW[r] / 2 + extra
        for (let i = 0; i < run; i++) {
          const j = start + i
          const x = L.roadXZ[j * 2], z = L.roadXZ[j * 2 + 1]
          const a = start + Math.max(0, i - 1), b = start + Math.min(run - 1, i + 1)
          const dx = L.roadXZ[b * 2] - L.roadXZ[a * 2], dz = L.roadXZ[b * 2 + 1] - L.roadXZ[a * 2 + 1], len = Math.hypot(dx, dz) || 1
          const ox = (-dz / len) * w, oz = (dx / len) * w
          pos.set([x - ox, y, z - oz, x + ox, y, z + oz], v * 6)
          if (i) { const p = (j - 1) * 2, q = j * 2; idx.set([p, p + 1, q, p + 1, q + 1, q], k * 6); k++ }
          v++
        }
        start += run
      })
      const g = this.own(new THREE.BufferGeometry())
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      g.setIndex(new THREE.BufferAttribute(idx, 1))
      this.scene.add(new THREE.Mesh(g, this.tint(new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }))))
    }
    ribbon(0.09, MAP_Y.road, '#d8c9b0')
    ribbon(0, MAP_Y.road + 0.01, '#fffdf8')
  }

  // a faint grid of latitude and longitude every 0.02°, as on a printed map
  private graticule() {
    const pts: number[] = []
    const y = MAP_Y.contour
    for (let lat = 11.72; lat <= 12.18; lat += 0.02) { const [x0, z] = toXZ(lat, 108.2), [x1] = toXZ(lat, 108.78); pts.push(x0, y, z, x1, y, z) }
    for (let lng = 108.2; lng <= 108.78; lng += 0.02) { const [x, z0] = toXZ(12.19, lng), [, z1] = toXZ(11.7, lng); pts.push(x, y, z0, x, y, z1) }
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    this.scene.add(new THREE.LineSegments(g, this.tint(new THREE.LineBasicMaterial({ color: '#c9b89c', transparent: true, opacity: 0.35, depthWrite: false }))))
  }

  // every place in the build, as a small golden dot on the map
  private places(points: [number, number][]) {
    const inside = points.filter(([lat, lng]) => inBounds(lat, lng))
    const pos = new Float32Array(inside.length * 3)
    inside.forEach(([lat, lng], i) => {
      const [x, z] = toXZ(lat, lng)
      const jx = Math.sin(i * 12.9) * 0.18, jz = Math.cos(i * 7.3) * 0.18 // places on one street do not merge
      pos.set([x + jx, MAP_Y.dot, z + jz], i * 3)
    })
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    const tex = this.own(radialTexture([[0, 'rgba(255,255,255,1)'], [0.32, 'rgba(255,255,255,1)'], [0.42, 'rgba(255,255,255,0.4)'], [1, 'rgba(255,255,255,0)']]))
    this.lightMat = this.own(new THREE.PointsMaterial({ color: C.sun, map: tex, size: 1.1, sizeAttenuation: true, transparent: true, depthWrite: false, opacity: this.still ? 1 : 0 }))
    this.scene.add(new THREE.Points(g, this.lightMat))
  }

  // the example day's places as postcards on white stems, rising out of the map
  private postcards(five: ScenePlace[]) {
    const stem = this.own(new THREE.CylinderGeometry(0.06, 0.06, STEM, 6))
    stem.translate(0, STEM / 2, 0)
    const stemMat = this.own(new THREE.MeshBasicMaterial({ color: '#ffffff' }))
    const ring = this.own(new THREE.RingGeometry(0.7, 1.05, 40))
    ring.rotateX(-Math.PI / 2)
    five.forEach((p, i) => {
      const [x, z] = toXZ(p.lat, p.lng)
      const group = new THREE.Group()
      group.position.set(x, 0, z)
      const mat = this.own(new THREE.SpriteMaterial({ map: postcard(null, this.brand), transparent: true, fog: false, rotation: (i % 2 ? 1 : -1) * 0.05 }))
      const card = new THREE.Sprite(mat)
      card.center.set(0.5, 0)
      card.position.y = STEM
      card.scale.set(CARD.w, CARD.h, 1)
      group.add(new THREE.Mesh(stem, stemMat), card)
      const r = new THREE.Mesh(ring, this.own(new THREE.MeshBasicMaterial({ color: this.brand, transparent: true, opacity: 0, depthWrite: false })))
      r.position.set(x, MAP_Y.route + 0.02, z)
      this.scene.add(group, r)
      this.cards.push({ group, ring: r, mat })
      this.cardTops.push(new THREE.Vector3(x, STEM + CARD.h, z))
      this.disposables.push({ dispose: () => mat.map?.dispose() })
      if (p.photo) {
        const img = new Image()
        img.decoding = 'async'
        this.loading++
        img.onload = () => {
          this.loading--
          mat.map?.dispose()
          mat.map = postcard(img, this.brand)
          mat.needsUpdate = true
          this.kick()
        }
        img.onerror = () => { this.loading-- }
        img.src = p.photo
      }
    })
  }

  // the stops in visiting order, as a terracotta dotted line drawn on the map (a travel map, not a ruler)
  private routeThrough(five: ScenePlace[]) {
    const pts: THREE.Vector3[] = []
    const ps = five.map((p) => toXZ(p.lat, p.lng))
    for (let i = 0; i < ps.length - 1; i++) {
      const [ax, az] = ps[i], [bx, bz] = ps[i + 1]
      const n = Math.max(4, Math.ceil(Math.hypot(bx - ax, bz - az) / 1.2))
      const nx = -(bz - az), nz = bx - ax, len = Math.hypot(nx, nz) || 1
      for (let k = 0; k < n; k++) {
        const t = k / n
        const bow = Math.sin(t * Math.PI) * 0.08 * Math.hypot(bx - ax, bz - az) * (i % 2 ? 1 : -1)
        pts.push(new THREE.Vector3(lerp(ax, bx, t) + (nx / len) * bow, MAP_Y.route, lerp(az, bz, t) + (nz / len) * bow))
      }
    }
    const [lx, lz] = ps[ps.length - 1]
    pts.push(new THREE.Vector3(lx, MAP_Y.route, lz))
    this.routeCurve = new THREE.CatmullRomCurve3(pts, false, 'centripetal')
    this.dashCount = Math.floor(this.routeCurve.getLength() / 1.1)
    const dash = this.own(new THREE.CapsuleGeometry(0.2, 0.45, 2, 8))
    dash.scale(1, 1, 0.25) // flat on the paper
    dash.rotateX(Math.PI / 2)
    this.dashes = new THREE.InstancedMesh(dash, this.own(new THREE.MeshBasicMaterial({ color: this.brand })), this.dashCount)
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), one = new THREE.Vector3(1, 1, 1)
    for (let i = 0; i < this.dashCount; i++) {
      const t = (i + 0.5) / this.dashCount
      const p = this.routeCurve.getPointAt(t), tan = this.routeCurve.getTangentAt(t)
      q.setFromAxisAngle(this.yAxis, Math.atan2(tan.x, tan.z))
      this.dashes.setMatrixAt(i, m.compose(p, q, one))
    }
    this.dashes.count = 0
    this.scene.add(this.dashes)
    // where each stop of the day lies along the route (0..1), for the page's timeline
    this.stopsAt = ps.map(([x, z]) => {
      let best = 0, bd = Infinity
      for (let i = 0; i <= 400; i++) {
        const p = this.routeCurve.getPointAt(i / 400)
        const d = (p.x - x) ** 2 + (p.z - z) ** 2
        if (d < bd) { bd = d; best = i / 400 }
      }
      return best
    })
  }

  // the share of the route (0..1) at which each stop of the example day lies
  get stops() {
    return this.stopsAt
  }

  // DOM labels that follow a postcard or an area on screen; the page owns the elements
  bindLabels(kind: 'five' | 'area', els: HTMLElement[], areas: ScenePlace[] = []) {
    this.labels = this.labels.filter((l) => l.kind !== kind)
    els.forEach((el, i) => {
      if (!el) return
      if (kind === 'five') this.labels.push({ el, at: this.cardTops[i], kind, i })
      else this.labels.push({ el, at: xz(areas[i].lat, areas[i].lng, 2), kind, i })
    })
    this.kick()
  }

  set(next: Partial<SceneState>) {
    // scrolling on to another view of the story hands the camera back to it
    if (next.cam !== undefined && Math.abs(next.cam - this.state.cam) > 1e-4 && !this.turn.drag) this.resetTurn()
    Object.assign(this.state, next)
    this.kick()
  }

  // turning the view: the page forwards pointer drags (pixels)
  dragStart() {
    this.turn.drag = true
    this.turn.vel = 0
  }

  dragBy(dxPx: number, dyPx: number) {
    const t = this.turn
    const dy = (dxPx / this.size.w) * Math.PI * 2.4
    t.yawT -= dy
    t.yaw -= dy // follow the hand 1:1 while it is down
    t.vel = -dy
    t.pitchT = Math.min(0.5, Math.max(-0.5, t.pitchT + (dyPx / this.size.h) * 1.4))
    this.kick()
  }

  dragEnd() {
    this.turn.drag = false
    this.kick()
  }

  // back to the story's own view, by the shortest way round
  private resetTurn() {
    const t = this.turn
    t.yawT = Math.round(t.yawT / (Math.PI * 2)) * Math.PI * 2
    t.pitchT = 0
    t.vel = 0
    this.kick()
  }

  // ---- free exploration ----
  setExplore(on: boolean) {
    const f = this.free
    if (on === f.on) return
    f.on = on
    if (on) {
      // start exactly where the story camera is, so nothing jumps
      const p = this.camera.position
      f.tT.copy(this.look).setY(0)
      const off = this.tmp.copy(p).sub(f.tT)
      f.dT = Math.min(320, Math.max(26, off.length()))
      f.yawT = Math.atan2(off.x, off.z)
      f.pitchT = Math.min(1.4, Math.max(0.2, Math.asin(Math.min(1, Math.max(-1, off.y / (off.length() || 1))))))
      f.t.copy(f.tT); f.d = f.dT; f.yaw = f.yawT; f.pitch = f.pitchT
      this.turn.vel = 0
    }
    this.kick()
  }

  // rotate (pixels) or, with `pan`, slide the view over the map
  exploreDrag(dx: number, dy: number, pan: boolean) {
    const f = this.free
    if (pan) this.explorePan(dx, dy)
    else {
      f.yawT -= (dx / this.size.w) * Math.PI * 2
      f.pitchT = Math.min(1.5, Math.max(0.15, f.pitchT + (dy / this.size.h) * 1.6))
    }
    this.kick()
  }

  explorePan(dxPx: number, dyPx: number) {
    const f = this.free
    const k = f.dT * 0.0016
    const sx = Math.cos(f.yawT), sz = -Math.sin(f.yawT) // screen right on the map
    const fx = -Math.sin(f.yawT), fz = -Math.cos(f.yawT) // away from the camera
    f.tT.x -= (dxPx * sx - dyPx * fx) * k
    f.tT.z -= (dxPx * sz - dyPx * fz) * k
    this.clampTarget()
    this.kick()
  }

  zoomBy(factor: number) {
    const f = this.free
    f.dT = Math.min(320, Math.max(14, f.dT * factor))
    this.kick()
  }

  rotateBy(dyaw: number) {
    this.free.yawT += dyaw
    this.kick()
  }

  // glide to a real place: its coordinates, and how close to look
  flyTo(lat: number, lng: number, dist: number) {
    const f = this.free
    f.tT.copy(xz(lat, lng))
    f.dT = dist
    f.pitchT = 0.75
    this.clampTarget()
    this.kick()
  }

  private clampTarget() {
    const t = this.free.tT
    t.x = Math.min(WORLD.w / 2 - 20, Math.max(-WORLD.w / 2 + 20, t.x))
    t.z = Math.min(WORLD.d / 2 - 20, Math.max(-WORLD.d / 2 + 20, t.z))
    t.y = 0
  }

  setPointer(x: number, y: number) {
    if (this.still || this.turn.drag) return
    this.pointer.set(x, y)
    this.kick()
  }

  resize(w: number, h: number) {
    this.size = { w: Math.max(1, w), h: Math.max(1, h) }
    this.renderer.setSize(this.size.w, this.size.h, false)
    this.camera.aspect = this.size.w / this.size.h
    this.kick()
  }

  // draw only while the scene is on screen
  setRunning(on: boolean) {
    this.running = on
    if (on) this.kick()
    else { cancelAnimationFrame(this.raf); this.raf = 0; this.last = 0; this.prevFrame = 0 }
  }

  // Shader programs compile on the GPU driver's own threads first (compileAsync), so the first frame does not stall
  // the page while they build; drawing starts once they are ready.
  private warmed: boolean | null = null
  private warm() {
    this.warmed = false
    const done = () => { this.warmed = true; this.kick() }
    this.renderer.compileAsync(this.scene, this.camera).then(done, done)
  }

  private kick() {
    if (!this.running || this.raf) return
    if (!this.warmed) {
      if (this.warmed === null) this.warm()
      return
    }
    this.raf = requestAnimationFrame(this.frame)
  }

  private frame = (now: number) => {
    this.raf = 0
    const t = (now - this.start) / 1000
    const dt = this.last ? Math.min(0.1, (now - this.last) / 1000) : 1 / 60
    this.last = now
    const moving = this.step(t, dt, this.still ? 1 : 1 - Math.exp(-dt * 6))
    this.govern(now)
    if (this.onReady) { const f = this.onReady; this.onReady = null; f() }
    // the cloud is always alive, so the loop runs while the scene is on screen; still mode draws on change only
    if (this.running && (!this.still || moving)) this.raf = requestAnimationFrame(this.frame)
    else { this.last = 0; this.prevFrame = 0 }
  }

  // One frame drawn at a given clock, for the pre-rendered landing (web/scripts/render_landing.mjs): the state is
  // shown exactly as set (no easing), and the label positions and the cloud's place come back with it.
  capture(t: number, dt: number) {
    this.step(t, dt, 1)
    return {
      labels: this.labelsOut.map((l) => [Math.round(l.x), Math.round(l.y), Math.round(l.o * 100) / 100]),
      mascot: this.mascotRect(),
      stops: this.stopsAt,
    }
  }

  get canvas() {
    return this.renderer.domElement
  }

  private labelsOut: { x: number; y: number; o: number }[] = []
  private loading = 0 // postcard photos still downloading (the pre-render waits for them)
  get busy() {
    return this.loading > 0
  }

  private step(t: number, dt: number, k: number) {
    let moving = false
    // ease toward the scrubbed state at the same speed whatever the frame rate
    for (const key of Object.keys(this.state) as (keyof SceneState)[]) {
      const d = this.state[key] - this.shown[key]
      if (Math.abs(d) > 0.0005) moving = true
      this.shown[key] = Math.abs(d) < 0.0005 ? this.state[key] : this.shown[key] + d * k
    }
    const tn = this.turn
    if (!tn.drag) {
      if (Math.abs(tn.vel) > 0.0004) { tn.yawT += tn.vel * dt * 24; tn.vel *= Math.exp(-dt * 3.2); moving = true } else tn.vel = 0
      const kt = this.still ? 1 : 1 - Math.exp(-dt * 5)
      if (Math.abs(tn.yawT - tn.yaw) > 0.0005 || Math.abs(tn.pitchT - tn.pitch) > 0.0005) moving = true
      tn.yaw += (tn.yawT - tn.yaw) * kt
      tn.pitch += (tn.pitchT - tn.pitch) * kt
    } else tn.pitch += (tn.pitchT - tn.pitch) * 0.35
    const fr = this.free
    const kb = this.still ? 1 : 1 - Math.exp(-dt * 3.5), kf = this.still ? 1 : 1 - Math.exp(-dt * 7)
    const gap = Math.abs(fr.d - fr.dT) + Math.abs(fr.yaw - fr.yawT) + Math.abs(fr.pitch - fr.pitchT) * 10 + fr.t.distanceTo(fr.tT)
    if (Math.abs((fr.on ? 1 : 0) - fr.blend) > 0.002 || (fr.on && gap > 0.01)) moving = true
    fr.blend = Math.abs((fr.on ? 1 : 0) - fr.blend) < 0.002 ? (fr.on ? 1 : 0) : fr.blend + ((fr.on ? 1 : 0) - fr.blend) * kb
    if (fr.on) {
      fr.t.lerp(fr.tT, kf)
      fr.d += (fr.dT - fr.d) * kf
      fr.yaw += (fr.yawT - fr.yaw) * kf
      fr.pitch += (fr.pitchT - fr.pitch) * kf
    }
    this.pointerShown.lerp(this.pointer, this.still ? 1 : 1 - Math.exp(-dt * 4))
    if (this.pointerShown.distanceTo(this.pointer) > 0.001) moving = true
    this.apply(t, this.still ? 5 : dt)
    this.renderer.render(this.scene, this.camera)
    this.project()
    return moving
  }

  // Quality governor: the scene is meant to run at the display's speed. When frames take much longer than 28 ms for a
  // good while (after a warm-up), drop the costliest extras one step at a time and never bring them back.
  private govern(now: number) {
    const g = this.slow
    if (this.still || !this.prevFrame) { this.prevFrame = now; return }
    const raw = now - this.prevFrame
    this.prevFrame = now
    if (raw > 250) return // a pause (tab hidden, long scroll gap), not slowness
    this.frames++
    if (this.frames < 30) return // shader compiles and texture uploads
    g.ema = g.ema * 0.92 + raw * 0.08
    if (g.ema < 28) { g.calm = 0; return }
    if (g.level >= 2) {
      // even the lowest quality cannot keep up: hand the page its light version
      if (++g.calm >= 90 && this.onGiveUp) { const f = this.onGiveUp; this.onGiveUp = null; f() }
      return
    }
    if (++g.calm < 40) return
    g.calm = 0
    g.level++
    g.ema = 16
    if (g.level === 1 && this.dpr > 1) {
      this.dpr = 1
      this.renderer.setPixelRatio(1)
      this.renderer.setSize(this.size.w, this.size.h, false)
    } else if (g.level === 2 && this.minorLines) this.minorLines.visible = false
  }

  // camera position for an orbit around `look`
  private orbit(look: THREE.Vector3, dist: number, pitch: number, yaw: number, out: THREE.Vector3) {
    const c = Math.cos(pitch) * dist
    return out.set(look.x + Math.sin(yaw) * c, look.y + Math.sin(pitch) * dist, look.z + Math.cos(yaw) * c)
  }

  private apply(t: number, dt: number) {
    const s = this.shown
    this.keys[4].look.copy(this.routeCurve.getPointAt(clamp01(s.travel))).setY(0)
    const i = Math.min(this.keys.length - 2, Math.floor(s.cam))
    const e = smooth(s.cam - i)
    const a = this.keys[i], b = this.keys[i + 1]
    this.look.lerpVectors(a.look, b.look, e)
    // keys are framed for a 16:10 window; step back on narrower ones so the map still fits
    const fit = Math.min(1.45, Math.max(1, 1.6 / this.camera.aspect))
    // distance eases in log space so a long zoom feels even
    let dist = Math.exp(lerp(Math.log(a.dist), Math.log(b.dist), e)) * fit
    let pitch = lerp(a.pitch, b.pitch, e)
    let yaw = lerp(a.yaw, b.yaw, e)
    // a slow breath in the hero, a little give under the pointer, the visitor's own turn, and the lift on leaving
    const breathe = this.still ? 0 : Math.sin(t * 0.25) * 0.03 * (1 - Math.min(1, s.cam))
    yaw += this.pointerShown.x * 0.05 + breathe + this.turn.yaw
    pitch = Math.min(1.45, Math.max(0.2, pitch + this.pointerShown.y * 0.03 + this.turn.pitch + s.lift * 0.18))
    dist *= 1 + s.lift * 0.4
    this.orbit(this.look, dist, pitch, yaw, this.camera.position)
    const fr = this.free, bl = fr.blend
    if (bl > 0.001) {
      const p = this.orbit(fr.t, fr.d, fr.pitch, fr.yaw, this.tmp)
      const eb = smooth(bl)
      this.camera.position.lerp(p, eb)
      this.look.lerp(fr.t, eb)
    }
    this.effFive = Math.max(s.five, bl)
    this.camera.lookAt(this.look)
    const { w, h } = this.size
    this.camera.setViewOffset(w, h, -s.shift * (1 - bl) * w, 0, w, h)
    this.camera.updateProjectionMatrix()
    this.camera.updateMatrixWorld()
    this.daylight(s.hour, s.lift)

    // dots fade in on load, then dim to faint grey when the day's places are chosen
    const dots = Math.max(s.dots, bl)
    this.lightMat.opacity = (this.still ? 1 : Math.min(1, t / 1.6)) * (0.2 + 0.8 * dots)
    this.lightMat.color.set(C.sun).lerp(this.grey, 1 - dots)
    const column = w * (s.shift + 0.24) * (1 - bl) // the text column on the left
    // a postcard standing between the camera and the walking cloud turns see-through, so the cloud stays in view
    const cloud = this.mascot.grounded ? this.mascotRect() : null
    const cloudDist = cloud ? this.camera.position.distanceTo(this.mascot.root.position) : 0
    this.cards.forEach(({ group, ring, mat }, n) => {
      const r = clamp01(this.effFive * 1.6 - n * 0.15)
      const k = 1 - Math.pow(1 - r, 3)
      // exploring: the postcards shrink (and more the closer the visitor flies) so they never bury the places beside them
      const small = 1 + (clamp01(this.free.d / 130) * 0.4 + 0.32 - 1) * bl
      group.scale.setScalar(k * small || 0.0001)
      group.visible = r > 0
      group.position.y = this.still ? 0 : Math.sin(t * 0.9 + n) * 0.25
      const pulse = this.still ? 0.5 : (Math.sin(t * 2.2 - n) + 1) / 2
      ;(ring.material as THREE.MeshBasicMaterial).opacity = r * (0.25 + 0.4 * pulse)
      ring.scale.setScalar(1 + pulse * 0.4)
      // a postcard behind the text column fades back so the words stay readable
      const sx = ((this.tmp.set(group.position.x, STEM + CARD.h / 2, group.position.z).project(this.camera).x + 1) / 2) * w
      const sy = ((1 - this.tmp.y) / 2) * this.size.h
      const covers = !!cloud && this.camera.position.distanceTo(group.position) < cloudDist && Math.abs(sx - cloud.x) < cloud.h * 0.8 && Math.abs(sy - cloud.y) < cloud.h * 0.9
      this.cardSee[n] = lerp(this.cardSee[n] ?? 1, covers ? 0.18 : 1, 1 - Math.exp(-dt * 8))
      mat.opacity = (column > 0 ? 0.12 + 0.88 * clamp01((sx - column * 0.85) / (column * 0.25)) : 1) * this.cardSee[n]
    })
    this.dashes.count = Math.floor(s.route * this.dashCount)
    this.stage(t, dt, bl)
  }

  // The day's light at `hour` (0 dawn, 0.5 noon, 1 sunset): the paper's tint, the sky and haze at the map's edge, the
  // light on the cloud; blended between the DAYLIGHT moments. Only colours and one light's place change.
  private daylight(hour: number, lift: number) {
    const h = clamp01(hour)
    const a = DAYLIGHT[h < 0.5 ? 0 : 1], b = DAYLIGHT[h < 0.5 ? 1 : 2], f = h < 0.5 ? h * 2 : (h - 0.5) * 2
    const mix = (x: string, y: string, out: THREE.Color) => out.set(x).lerp(this.c1.set(y), f)
    const tint = mix(a.tint, b.tint, this.tint1)
    for (const { mat, base } of this.tinted) mat.color.copy(base).multiply(tint)
    const u = this.sky_.uniforms
    mix(a.top, b.top, u.top.value)
    mix(a.low, b.low, u.low.value)
    const fog = this.scene.fog as THREE.Fog
    fog.color.copy(u.low.value)
    fog.near = lerp(160, 30, lift)
    fog.far = lerp(520, 260, lift)
    mix(a.sun, b.sun, this.sunLight.color)
    this.sunLight.intensity = lerp(a.sunI, b.sunI, f)
    this.sunLight.position.set(lerp(a.sunAt[0], b.sunAt[0], f), lerp(a.sunAt[1], b.sunAt[1], f), lerp(a.sunAt[2], b.sunAt[2], f))
    mix(a.hemi[0], b.hemi[0], this.hemi.color)
    mix(a.hemi[1], b.hemi[1], this.hemi.groundColor)
  }

  // The cloud's part in each beat (docs/UI_SPEC_LANDING.md §2). It always flies in front of the camera, big, and
  // drifts around its perch like a fish; between beats it swoops on an arc to the next perch and squashes when it
  // settles. Acts: hover (map open), listen (headset, "…"), pick (holds the map up), evidence (turns to the postcard),
  // walk (flies ahead along the route), stamp and wave at the last stop.
  private stage(t: number, dt: number, bl: number) {
    const m = this.mascot, s = this.shown, cam = this.camera, root = m.root
    root.visible = !this.mascotHidden
    const c = Math.min(5, Math.max(0, s.cam))
    const i = Math.min(4, Math.floor(c)), f = c - i
    const pa = PERCH[i], pb = PERCH[i + 1], e = smooth(f)
    const at = this.v1.set(lerp(pa.at[0], pb.at[0], e), lerp(pa.at[1], pb.at[1], e), lerp(pa.at[2], pb.at[2], e))
    let size = lerp(pa.size, pb.size, e)
    const air = f > 0.02 && f < 0.98 ? Math.sin(Math.PI * f) : 0
    at.y += air * 0.9
    // the drift: a slow, never-repeating loop around the perch
    const drift = this.still ? 0 : lerp(pa.drift, pb.drift, e)
    at.x += (Math.sin(t * 0.37) * 0.3 + Math.sin(t * 0.13 + 2) * 0.15) * drift // narrow: the chapter rail is on the right
    at.y += Math.sin(t * 0.53 + 1) * 0.25 * drift
    at.z += Math.sin(t * 0.21) * 1.4 * drift
    // free exploration: it keeps to a corner, watching
    if (bl > 0.001) {
      const eb = smooth(bl)
      at.lerp(this.v2.set(...PERCH_FREE.at), eb)
      size = lerp(size, PERCH_FREE.size, eb)
    }
    root.position.copy(at).applyMatrix4(cam.matrixWorld)
    // From the itinerary on it leaves the camera's side and lands on the map itself: it stands on the route, walks it
    // with its feet on the paper and keeps its size relative to the map, not to the screen.
    const eb = bl > 0.001 ? smooth(bl) : 0
    const w = smooth(clamp01((c - 3.1) / 0.6)) * (1 - eb)
    if (w > 0.001) {
      const ground = this.v3.copy(this.routeCurve.getPointAt(clamp01(s.travel)))
      ground.y = MAP_Y.route
      const d = cam.position.distanceTo(ground)
      const walkSize = d * 0.075
      // at the last stop it steps in front of the stop's postcard to stamp
      const aside = clamp01(s.stamp * 3) * walkSize * 0.9
      ground.x += Math.sign(cam.position.x - ground.x || 1) * aside * 0.3
      ground.z += (cam.position.z > ground.z ? 1 : -1) * aside
      root.position.lerp(ground, w)
      root.position.y += Math.sin(Math.PI * w) * d * 0.08 // the landing arc
      size = lerp(size, walkSize, w)
    }
    root.scale.setScalar(size)
    // facing the camera, turned a little toward where it drifts (and along the route while it flies it)
    let turn = Math.cos(t * 0.37) * 0.35 * drift
    let act: MascotAct = 'hover', k = 1
    let look: THREE.Vector3 | null = null
    const pointer = () => this.v2.set(this.pointerShown.x * 10, this.pointerShown.y * 6, 0).applyMatrix4(cam.matrixWorld)
    if (c < 0.5) look = pointer()
    else if (c < 1.5) { act = 'listen'; k = clamp01((c - 0.5) * 2.5); look = pointer() }
    else if (c < 2.5) { act = 'pick'; k = clamp01((c - 1.5) * 2) }
    else if (c < 3.5) { act = 'pick'; k = 0.3; look = this.focusLook }
    else if (s.stamp < 0.01) {
      act = 'walk'
      k = s.travel
      // fly the way the route runs on screen
      const tan = this.routeCurve.getTangentAt(clamp01(s.travel)).transformDirection(cam.matrixWorldInverse)
      turn = Math.max(-0.45, Math.min(0.45, Math.atan2(tan.x, Math.abs(tan.z) + 0.6) * 0.55))
    } else {
      act = s.stamp > 0.6 ? 'wave' : 'stamp'
      k = act === 'stamp' ? s.stamp / 0.6 : 1
    }
    if (bl > 0.5) { act = 'hover'; k = 1; look = pointer() }
    if (!look && act !== 'walk') look = cam.position
    root.quaternion.copy(cam.quaternion).multiply(this.qa.setFromAxisAngle(this.yAxis, turn))
    if (w > 0.001) {
      // upright on the map, facing the camera (turned along the route), leaning back a little so the face stays readable
      const yaw = Math.atan2(cam.position.x - root.position.x, cam.position.z - root.position.z)
      root.quaternion.slerp(this.qb.setFromAxisAngle(this.yAxis, yaw + turn), w)
    }
    m.setTilt(w * 0.3)
    m.setRoute(this.routeCurve.getLength())
    m.setGround(w > 0.97)
    m.set(act, k)
    m.lookAt(look)
    m.setAir(air)
    m.update(dt)
  }

  // Where the cloud is on screen (CSS px in the canvas: centre and height), for the page's hand-off to the app logo;
  // null when it is hidden.
  mascotRect() {
    const root = this.mascot.root
    if (!root.visible) return null
    const { w, h } = this.size
    root.updateMatrixWorld()
    const top = this.tmp.set(0, this.mascot.height, 0).applyMatrix4(root.matrixWorld).project(this.camera)
    const x1 = ((top.x + 1) / 2) * w, y1 = ((1 - top.y) / 2) * h
    const foot = this.tmp.copy(root.position).project(this.camera)
    if (foot.z > 1) return null
    const x0 = ((foot.x + 1) / 2) * w, y0 = ((1 - foot.y) / 2) * h
    return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, h: Math.hypot(x1 - x0, y1 - y0) }
  }

  // hide the 3D cloud (its DOM stand-in takes over for the page transition)
  hideMascot(on: boolean) {
    this.mascotHidden = on
    this.kick()
  }

  private project() {
    const { w, h } = this.size
    // labels are drawn over the canvas: one that would land on the cloud steps aside
    const cloud = this.mascotRect()
    const onCloud = (x: number, y: number) => !!cloud && Math.abs(x - cloud.x) < cloud.h * 0.75 && Math.abs(y - cloud.y) < cloud.h * 0.65
    this.labelsOut = []
    for (const l of this.labels) {
      if (l.kind === 'five') {
        const g = this.cards[l.i].group
        this.tmp.set(g.position.x, g.position.y + (STEM + CARD.h) * g.scale.y + 0.6, g.position.z)
      } else this.tmp.copy(l.at)
      this.tmp.project(this.camera)
      const bl = this.free.blend
      const vis = l.kind === 'five' ? clamp01(this.effFive * 1.6 - l.i * 0.15 - 0.4) : Math.max(this.shown.areas, bl)
      const sx = ((this.tmp.x + 1) / 2) * w, sy = ((1 - this.tmp.y) / 2) * h
      // labels never sit under the text column, half off the edge (the column is gone while exploring) or on the cloud
      const hidden = this.tmp.z > 1 || sx < w * (this.shown.shift + 0.24) * (1 - bl) || sx > w - 80 * (1 - bl) || onCloud(sx, sy)
      l.el.style.transform = `translate3d(${sx}px, ${sy}px, 0)`
      l.el.style.opacity = hidden ? '0' : String(vis)
      this.labelsOut.push({ x: sx, y: sy, o: hidden ? 0 : vis })
    }
  }

  dispose() {
    this.running = false
    cancelAnimationFrame(this.raf)
    this.mascot?.dispose()
    this.disposables.forEach((d) => d.dispose())
    this.renderer.dispose()
  }
}

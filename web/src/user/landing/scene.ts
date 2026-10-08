import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { GRID, inBounds, LANDMARKS, toXZ, WORLD } from './geo'
import { decodeLandscape, groundAt, heightAt, landscape, setLandscape } from './terrain'

// The landing's 3D scene (docs/UI_SPEC_LANDING.md §2): the real Đà Lạt valley at sunrise in soft rose. Plain three.js,
// driven from outside: the page scrubs `SceneState` with GSAP; the scene only eases toward it and draws. On top of the
// scrubbed camera the visitor can turn the whole view 360° around the valley (drag, or the page's buttons).

export interface ScenePlace { name: string; lat: number; lng: number; photo?: string }
export interface SceneState {
  cam: number // camera keyframe, 0..5 (hero, understand, choose, evidence, itinerary, feedback)
  dots: number // 1 = every place lit, 0 = only the chosen five
  five: number // 0..1 the five postcards rising
  route: number // 0..1 drawn share of the route
  travel: number // 0..1 marker along the route; 0 hides it
  areas: number // 0..1 area labels and morning mist
  shift: number // horizontal framing: share of the width kept free for text on the left
}

// the soft rose system of the landing (css/landing.css): blush sky, rose hills, plum pines, golden lamps
const C = {
  sun: '#f4b43c', // the places: warm lamps, the one yellow in the scene
  rose: '#c97890', // rings, stamps
  plum: '#6b3550',
  paper: '#fff9f8',
  blush: '#fceef1',
  ink3: '#7d6873',
  water: '#aebfee',
}
const HORIZON = '#fbd9d6' // where the fog meets the sky

// camera keyframes from real places (north is -z): the pivot is what the visitor's 360° turn circles around
type Key = { pos: [number, number, number]; look: [number, number, number]; pivot: [number, number, number] }
function buildKeys(): Key[] {
  const at = (lat: number, lng: number, up: number): [number, number, number] => {
    const [x, z] = toXZ(lat, lng)
    return [x, groundAt(x, z) + up, z]
  }
  return [
    { pos: at(11.862, 108.412, 20), look: at(11.99, 108.47, 6), pivot: at(11.942, 108.443, 0) }, // hero: from the Tuyền Lâm hills, up the valley to the town and Langbiang
    { pos: at(11.93, 108.385, 26), look: at(11.945, 108.445, 2), pivot: at(11.945, 108.445, 0) }, // understand: drift round to the west of town
    { pos: at(11.83, 108.49, 104), look: at(11.935, 108.45, 0), pivot: at(11.935, 108.45, 0) }, // choose: rise up to see the whole route
    { pos: [0, 0, 0], look: [0, 0, 0], pivot: [0, 0, 0] }, // evidence: filled from the focus postcard
    { pos: at(11.85, 108.41, 74), look: at(11.935, 108.45, 0), pivot: at(11.935, 108.45, 0) }, // itinerary: the day's route, wide
    { pos: at(11.86, 108.55, 34), look: at(11.99, 108.38, 14), pivot: at(11.942, 108.443, 0) }, // feedback: rise back over the valley toward Langbiang
  ]
}

// Tones for the baked instances (the baker stores only an index); sRGB hex like everything else on the page.
const TREE_TONES = ['#b27693', '#c487a2', '#a0657f', '#cf97ae', '#b98099']
const HOUSE_TONES = ['#f2a9b8', '#e8909f', '#f7bfc9', '#dd7f93'] // rose roofs, never golden: only the lamps are places
const BLOSSOM_TONES = ['#ffc4d6', '#ffadc8', '#f9a3c0', '#ffd6e2', '#f6b6d0']

// place baked instances (x, z, width, height, turn) on the ground
function place(mesh: THREE.InstancedMesh, a: Float32Array, tones: number[] | Uint8Array, palette: string[], sink: number, y1 = false) {
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0)
  const cols = palette.map((h) => new THREE.Color(h))
  const n = a.length / 5
  for (let i = 0; i < n; i++) {
    const x = a[i * 5], z = a[i * 5 + 1]
    q.setFromAxisAngle(up, a[i * 5 + 4])
    s.set(a[i * 5 + 2], y1 ? a[i * 5 + 2] : a[i * 5 + 3], a[i * 5 + 2])
    mesh.setMatrixAt(i, m.compose(p.set(x, heightAt(x, z) - sink, z), q, s))
    mesh.setColorAt(i, cols[tones[i] % cols.length])
  }
  mesh.count = n
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const STEM = 4.5
const CARD = { w: 6.2, h: 7.4 }

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
function postcard(img: HTMLImageElement | null) {
  const W = 248, H = 296, B = 12, R = 14
  const c = document.createElement('canvas')
  c.width = W + 24
  c.height = H + 24
  const g = c.getContext('2d')!
  g.translate(12, 8)
  g.shadowColor = 'rgba(107,53,80,0.3)'
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
    grad.addColorStop(0, C.blush)
    grad.addColorStop(1, '#efc3cf')
    g.fillStyle = grad
    g.fillRect(B, B, iw, ih)
  }
  g.restore()
  // two short ruled lines where a postcard's message would go, and a sun stamp
  g.fillStyle = '#f3e1e4'
  g.fillRect(B, H - 26, iw * 0.55, 3)
  g.fillRect(B, H - 17, iw * 0.35, 3)
  g.fillStyle = C.rose
  g.beginPath()
  g.arc(W - B - 8, H - 18, 6, 0, Math.PI * 2)
  g.fill()
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

export interface SceneData { points: [number, number][]; five: ScenePlace[]; focus: number; land: ArrayBuffer }

export class DalatScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(38, 1, 1, 1600)
  private state: SceneState = { cam: 0, dots: 1, five: 0, route: 0, travel: 0, areas: 1, shift: 0.2 }
  private shown: SceneState = { ...this.state }
  private pointer = new THREE.Vector2()
  private pointerShown = new THREE.Vector2()
  private lightMat!: THREE.PointsMaterial
  private cards: { group: THREE.Group; ring: THREE.Mesh }[] = []
  private cardTops: THREE.Vector3[] = []
  private dashes!: THREE.InstancedMesh
  private dashCount = 0
  private routeCurve!: THREE.CatmullRomCurve3
  private rider!: THREE.Mesh
  private mist: THREE.Sprite[] = []
  private rays_: THREE.Sprite[] = []
  private petalBase = new Float32Array(0)
  private petalMat!: THREE.PointsMaterial
  private petalPts!: THREE.Points
  private flyMat!: THREE.PointsMaterial
  private labels: { el: HTMLElement; at: THREE.Vector3; kind: 'five' | 'area'; i: number }[] = []
  private keys!: { pos: THREE.Vector3; look: THREE.Vector3; pivot: THREE.Vector3 }[]
  private treeMesh: THREE.InstancedMesh | null = null
  private treeFull = 0
  private prevFrame = 0
  private frames = 0
  private flyPts!: THREE.Points
  private fx = true // particles, rays and fireflies; the first thing a slow machine drops
  private dpr = 1
  private slow = { ema: 16, level: 0, calm: 0 }
  onReady: (() => void) | null = null
  private size = { w: 1, h: 1 }
  private raf = 0
  private running = false
  private start = performance.now()
  private last = 0
  private tmp = new THREE.Vector3()
  private look = new THREE.Vector3()
  private grey = new THREE.Color(C.ink3)
  private disposables: { dispose(): void }[] = []
  // the visitor's own turn on top of the scrubbed camera: yaw 360° around the pivot, pitch up and down
  private turn = { yaw: 0, yawT: 0, pitch: 0, pitchT: 0, vel: 0, drag: false, swing: -1 }
  private pivot = new THREE.Vector3()
  onTurn: (() => void) | null = null

  static create(canvas: HTMLCanvasElement, data: SceneData, still: boolean) {
    try {
      return new DalatScene(canvas, data, still)
    } catch {
      return null // no WebGL: the page keeps its photo fallback
    }
  }

  private constructor(canvas: HTMLCanvasElement, data: SceneData, private still: boolean) {
    setLandscape(decodeLandscape(data.land))
    performance.mark('tg-build:decode')
    this.keys = buildKeys().map((k) => ({ pos: new THREE.Vector3(...k.pos), look: new THREE.Vector3(...k.look), pivot: new THREE.Vector3(...k.pivot) }))
    // a screen at 2x or more is sharp enough without multisampling, and it costs a lot of fill rate
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: devicePixelRatio < 2, powerPreference: 'high-performance' })
    this.dpr = Math.min(devicePixelRatio, 1.5)
    this.renderer.setPixelRatio(this.dpr)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.NoToneMapping
    // the valley does not move: the sun's shadows are drawn once (see frame) instead of every frame
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.autoUpdate = false
    this.renderer.shadowMap.needsUpdate = true
    this.scene.fog = new THREE.Fog(HORIZON, 70, 380)
    // each step leaves a performance mark (tg-build:<step>): the load profile in the browser's Performance panel
    const lap = (step: string) => performance.mark(`tg-build:${step}`)
    lap('renderer')
    this.sky(); lap('sky')
    this.light(); lap('light')
    this.terrain(); lap('terrain')
    this.forest(); lap('forest')
    this.town(); lap('town')
    this.roads(); lap('roads')
    this.places(data.points); lap('places')
    this.postcards(data.five); lap('postcards')
    this.routeThrough(data.five); lap('route')
    this.mistLayers(); lap('mist')
    this.rays(); lap('rays')
    this.blossoms(); lap('blossoms')
    this.petals(); lap('petals')
    this.fireflies(); lap('fireflies')
    // evidence keyframe: eye level with the focus postcard, a little to its right
    const f = this.cardTops[data.focus]
    this.keys[3].look.copy(f).add(new THREE.Vector3(0, -CARD.h * 0.55, 0))
    this.keys[3].pos.copy(f).add(new THREE.Vector3(14, 1, 30))
    this.keys[3].pivot.set(f.x, f.y - CARD.h * 0.55, f.z)
  }

  private own<T extends { dispose(): void }>(x: T) {
    this.disposables.push(x)
    return x
  }

  // sky dome: pale pine at the top, paper in the middle, peach at the horizon; a low sun in the east
  private sky() {
    const geo = this.own(new THREE.SphereGeometry(900, 32, 16))
    const mat = this.own(new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
      uniforms: { top: { value: new THREE.Color('#e7d9f3') }, mid: { value: new THREE.Color(C.paper) }, low: { value: new THREE.Color(HORIZON) } },
      vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'uniform vec3 top; uniform vec3 mid; uniform vec3 low; varying vec3 vP; void main(){ float h = vP.y; vec3 c = h > 0.18 ? mix(mid, top, smoothstep(0.18, 0.75, h)) : mix(low, mid, smoothstep(-0.02, 0.18, h)); gl_FragColor = vec4(c, 1.0); }',
    }))
    this.scene.add(new THREE.Mesh(geo, mat))
    const glow = new THREE.Sprite(this.own(new THREE.SpriteMaterial({ map: this.own(radialTexture([[0, 'rgba(255,224,190,1)'], [0.18, 'rgba(255,196,170,0.85)'], [0.45, 'rgba(252,208,205,0.38)'], [1, 'rgba(252,225,228,0)']])), transparent: true, depthWrite: false, fog: false })))
    glow.position.set(160, 70, -620)
    glow.scale.set(760, 760, 1)
    this.scene.add(glow)
  }

  private light() {
    this.scene.add(new THREE.HemisphereLight('#fff0f3', '#dcc0e0', 1.45))
    const sun = new THREE.DirectionalLight('#ffd8c8', 2.6)
    sun.position.set(140, 70, -110)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    const s = sun.shadow.camera
    s.left = -110; s.right = 110; s.top = 90; s.bottom = -90; s.near = 20; s.far = 420
    sun.shadow.bias = -0.0006
    sun.shadow.normalBias = 0.5
    this.scene.add(sun)
  }

  // the ground and the lakes, straight from the baked grid
  private terrain() {
    const L = landscape()
    const { cols, rows } = L
    const pos = new Float32Array(cols * rows * 3)
    for (let iz = 0, i = 0; iz < rows; iz++)
      for (let ix = 0; ix < cols; ix++, i++) pos.set([(ix / GRID.nx) * WORLD.w - WORLD.w / 2, L.height[i], (iz / GRID.nz) * WORLD.d - WORLD.d / 2], i * 3)
    // sRGB bytes to the linear working space through a 256-entry table
    const lut = new Float32Array(256)
    const t = new THREE.Color()
    for (let v = 0; v < 256; v++) lut[v] = t.setRGB(v / 255, 0, 0, THREE.SRGBColorSpace).r
    const col = new Float32Array(cols * rows * 3)
    for (let i = 0; i < col.length; i++) col[i] = lut[L.color[i]]
    const idx = new Uint32Array(GRID.nx * GRID.nz * 6)
    for (let iz = 0, k = 0; iz < GRID.nz; iz++)
      for (let ix = 0; ix < GRID.nx; ix++) {
        const a = iz * cols + ix, b = a + 1, c = a + cols, d = c + 1
        idx.set([a, c, b, b, c, d], k)
        k += 6
      }
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('color', new THREE.BufferAttribute(col, 3))
    g.setIndex(new THREE.BufferAttribute(idx, 1))
    g.computeVertexNormals()
    const land = new THREE.Mesh(g, this.own(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 })))
    land.receiveShadow = true
    land.castShadow = true
    this.scene.add(land)

    // every lake in one mesh, each at its own level: Hồ Xuân Hương and Hồ Tuyền Lâm differ by tens of metres
    const wg = this.own(new THREE.BufferGeometry())
    wg.setAttribute('position', new THREE.BufferAttribute(L.waterPos, 3))
    wg.setIndex(new THREE.BufferAttribute(L.waterIdx, 1))
    this.scene.add(new THREE.Mesh(wg, this.own(new THREE.MeshStandardMaterial({ color: C.water, roughness: 0.2, metalness: 0.1, emissive: '#cdd8fb', emissiveIntensity: 0.3 }))))
  }

  // Đà Lạt's pines (thông ba lá): a slim trunk under three tiers of canopy, wherever the map says forest and on the
  // unworked hills around the town
  private forest() {
    const L = landscape()
    const tier = (r: number, h: number, y: number) => { const t = new THREE.ConeGeometry(r, h, 7); t.translate(0, y + h / 2, 0); return t }
    const trunk = new THREE.CylinderGeometry(0.05, 0.08, 0.6, 5)
    trunk.translate(0, 0.3, 0)
    const tree = this.own(mergeGeometries([trunk, tier(0.58, 0.95, 0.45), tier(0.44, 0.85, 0.95), tier(0.29, 0.75, 1.45)], false))
    const mesh = new THREE.InstancedMesh(tree, this.own(new THREE.MeshStandardMaterial({ roughness: 0.85, flatShading: true })), L.treeTone.length)
    place(mesh, L.trees, L.treeTone, TREE_TONES, 0.1)
    mesh.castShadow = true
    mesh.receiveShadow = true
    this.treeMesh = mesh
    this.treeFull = mesh.count
    this.scene.add(mesh)
  }

  // the town: a villa at every mapped building (thinned), rose roofs, and the cathedral with its rooster
  private town() {
    const L = landscape()
    const wall = this.own(new THREE.BoxGeometry(0.5, 0.36, 0.5))
    wall.translate(0, 0.18, 0)
    const roof = this.own(new THREE.ConeGeometry(0.44, 0.34, 4))
    roof.rotateY(Math.PI / 4)
    roof.translate(0, 0.53, 0)
    const n = L.houseTone.length
    const walls = new THREE.InstancedMesh(wall, this.own(new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.8 })), n)
    const roofs = new THREE.InstancedMesh(roof, this.own(new THREE.MeshStandardMaterial({ roughness: 0.7, flatShading: true })), n)
    place(roofs, L.houses, L.houseTone, HOUSE_TONES, 0.04, true)
    place(walls, L.houses, L.houseTone, ['#ffffff'], 0.04, true)
    for (const mesh of [walls, roofs]) {
      mesh.castShadow = true
      mesh.receiveShadow = true
      this.scene.add(mesh)
    }

    // Nhà thờ Chánh Tòa: a nave, a slim bell tower and the rooster on top
    const [cx, cz] = LANDMARKS.cathedral
    const base = heightAt(cx, cz)
    const white = this.own(new THREE.MeshStandardMaterial({ color: '#fffafa', roughness: 0.7 }))
    const rose = this.own(new THREE.MeshStandardMaterial({ color: '#d9728c', roughness: 0.6, flatShading: true }))
    const nave = new THREE.Mesh(this.own(new THREE.BoxGeometry(1.5, 0.7, 0.8)), white)
    nave.position.set(cx, base + 0.35, cz)
    const tower = new THREE.Mesh(this.own(new THREE.BoxGeometry(0.42, 2.0, 0.42)), white)
    tower.position.set(cx - 0.7, base + 1.0, cz)
    const spire = new THREE.Mesh(this.own(new THREE.ConeGeometry(0.34, 1.0, 4)), rose)
    spire.position.set(cx - 0.7, base + 2.5, cz)
    spire.rotation.y = Math.PI / 4
    const cock = new THREE.Mesh(this.own(new THREE.SphereGeometry(0.1, 10, 8)), rose)
    cock.position.set(cx - 0.7, base + 3.08, cz)
    for (const o of [nave, tower, spire, cock]) { o.castShadow = true; this.scene.add(o) }
  }

  // main roads (trunk to tertiary) laid on the ground as pale ribbons, from the baked centre lines
  private roads() {
    const L = landscape()
    const points = L.roadXZ.length / 2
    const pos = new Float32Array(points * 6)
    const idx = new Uint32Array((points - L.roadRuns.length) * 6)
    let v = 0, k = 0, start = 0
    L.roadRuns.forEach((run, r) => {
      const w = L.roadW[r] / 2
      for (let i = 0; i < run; i++) {
        const j = start + i
        const x = L.roadXZ[j * 2], z = L.roadXZ[j * 2 + 1]
        const a = start + Math.max(0, i - 1), b = start + Math.min(run - 1, i + 1)
        const dx = L.roadXZ[b * 2] - L.roadXZ[a * 2], dz = L.roadXZ[b * 2 + 1] - L.roadXZ[a * 2 + 1], len = Math.hypot(dx, dz) || 1
        const ox = (-dz / len) * w, oz = (dx / len) * w, y = groundAt(x, z) + 0.12
        pos.set([x - ox, y, z - oz, x + ox, y, z + oz], v * 6)
        if (i) { const p = (j - 1) * 2, q = j * 2; idx.set([p, p + 1, q, p + 1, q + 1, q], k * 6); k++ }
        v++
      }
      start += run
    })
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setIndex(new THREE.BufferAttribute(idx, 1))
    this.scene.add(new THREE.Mesh(g, this.own(new THREE.MeshBasicMaterial({ color: '#fffaf6', transparent: true, opacity: 0.85, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }))))
  }

  // every place in the build, as a warm light in the valley
  private places(points: [number, number][]) {
    const inside = points.filter(([lat, lng]) => inBounds(lat, lng))
    const pos = new Float32Array(inside.length * 3)
    inside.forEach(([lat, lng], i) => {
      const [x, z] = toXZ(lat, lng)
      const jx = Math.sin(i * 12.9) * 0.18, jz = Math.cos(i * 7.3) * 0.18 // places on one street do not merge
      pos.set([x + jx, groundAt(x + jx, z + jz) + 0.7, z + jz], i * 3)
    })
    const g = this.own(new THREE.BufferGeometry())
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    const tex = this.own(radialTexture([[0, 'rgba(255,255,255,1)'], [0.28, 'rgba(255,255,255,1)'], [0.36, 'rgba(255,255,255,0.5)'], [1, 'rgba(255,255,255,0)']]))
    this.lightMat = this.own(new THREE.PointsMaterial({ color: C.sun, map: tex, size: 1.25, sizeAttenuation: true, transparent: true, depthWrite: false, opacity: this.still ? 1 : 0 }))
    this.scene.add(new THREE.Points(g, this.lightMat))
  }

  private postcards(five: ScenePlace[]) {
    const stem = this.own(new THREE.CylinderGeometry(0.06, 0.06, STEM, 6))
    stem.translate(0, STEM / 2, 0)
    const stemMat = this.own(new THREE.MeshBasicMaterial({ color: '#ffffff' }))
    const ring = this.own(new THREE.RingGeometry(0.7, 1.05, 40))
    ring.rotateX(-Math.PI / 2)
    five.forEach((p, i) => {
      const [x, z] = toXZ(p.lat, p.lng)
      const y = groundAt(x, z)
      const group = new THREE.Group()
      group.position.set(x, y, z)
      const mat = this.own(new THREE.SpriteMaterial({ map: postcard(null), transparent: true, fog: false, rotation: (i % 2 ? 1 : -1) * 0.05 }))
      const card = new THREE.Sprite(mat)
      card.center.set(0.5, 0)
      card.position.y = STEM
      card.scale.set(CARD.w, CARD.h, 1)
      group.add(new THREE.Mesh(stem, stemMat), card)
      const r = new THREE.Mesh(ring, this.own(new THREE.MeshBasicMaterial({ color: C.rose, transparent: true, opacity: 0, depthWrite: false })))
      r.position.set(x, y + 0.08, z)
      this.scene.add(group, r)
      this.cards.push({ group, ring: r })
      this.cardTops.push(new THREE.Vector3(x, y + STEM + CARD.h, z))
      this.disposables.push({ dispose: () => mat.map?.dispose() })
      if (p.photo) {
        const img = new Image()
        img.decoding = 'async'
        img.onload = () => {
          mat.map?.dispose()
          mat.map = postcard(img)
          mat.needsUpdate = true
          this.kick()
        }
        img.src = p.photo
      }
    })
  }

  // the five in visiting order, as a dotted line laid over the ground (a travel map, not a ruler)
  private routeThrough(five: ScenePlace[]) {
    const pts: THREE.Vector3[] = []
    const xz = five.map((p) => toXZ(p.lat, p.lng))
    for (let i = 0; i < xz.length - 1; i++) {
      const [ax, az] = xz[i], [bx, bz] = xz[i + 1]
      const n = Math.max(4, Math.ceil(Math.hypot(bx - ax, bz - az) / 1.2))
      const nx = -(bz - az), nz = bx - ax, len = Math.hypot(nx, nz) || 1
      for (let k = 0; k < n; k++) {
        const t = k / n
        const bow = Math.sin(t * Math.PI) * 0.08 * Math.hypot(bx - ax, bz - az) * (i % 2 ? 1 : -1)
        const x = lerp(ax, bx, t) + (nx / len) * bow, z = lerp(az, bz, t) + (nz / len) * bow
        pts.push(new THREE.Vector3(x, groundAt(x, z) + 0.5, z))
      }
    }
    const [lx, lz] = xz[xz.length - 1]
    pts.push(new THREE.Vector3(lx, groundAt(lx, lz) + 0.5, lz))
    this.routeCurve = new THREE.CatmullRomCurve3(pts, false, 'centripetal')
    this.dashCount = Math.floor(this.routeCurve.getLength() / 1.1)
    const dash = this.own(new THREE.CapsuleGeometry(0.22, 0.45, 4, 8))
    dash.rotateX(Math.PI / 2)
    this.dashes = new THREE.InstancedMesh(dash, this.own(new THREE.MeshStandardMaterial({ color: '#b83a74', emissive: '#b83a74', emissiveIntensity: 0.45, roughness: 0.5 })), this.dashCount)
    const m = new THREE.Matrix4(), up = new THREE.Vector3(0, 1, 0)
    for (let i = 0; i < this.dashCount; i++) {
      const t = (i + 0.5) / this.dashCount
      const p = this.routeCurve.getPointAt(t)
      const ahead = this.routeCurve.getPointAt(Math.min(1, t + 0.002))
      m.lookAt(ahead, p, up).setPosition(p)
      this.dashes.setMatrixAt(i, m)
    }
    this.dashes.count = 0
    this.scene.add(this.dashes)
    this.rider = new THREE.Mesh(this.own(new THREE.SphereGeometry(0.7, 20, 14)), this.own(new THREE.MeshStandardMaterial({ color: C.plum, emissive: C.rose, emissiveIntensity: 0.5 })))
    this.rider.visible = false
    this.scene.add(this.rider)
  }

  // Đà Lạt's morning mist: low layers lying in the real basins (the town, Tuyền Lâm, Trại Mát, the Đa Nhim side), drifting slowly
  private mistLayers() {
    const tex = this.own(radialTexture([[0, 'rgba(255,248,250,0.9)'], [0.55, 'rgba(255,240,246,0.45)'], [1, 'rgba(255,240,246,0)']]))
    const spots: [number, number, number][] = [[11.945, 108.43, 70], [11.89, 108.42, 80], [11.95, 108.5, 90], [11.99, 108.47, 80], [11.88, 108.55, 100], [12.02, 108.39, 80], [11.84, 108.5, 110], [11.96, 108.33, 120], [11.78, 108.45, 140], [12.1, 108.5, 140]]
    spots.forEach(([lat, lng, s]) => {
      const [x, z] = toXZ(lat, lng)
      const sp = new THREE.Sprite(this.own(new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0.6, depthWrite: false })))
      sp.position.set(x, groundAt(x, z) + 3, z)
      sp.scale.set(s, s * 0.22, 1)
      sp.userData = { x, s: 0.3 + Math.random() * 0.5, p: Math.random() * 6 }
      this.mist.push(sp)
      this.scene.add(sp)
    })
  }

  // first light fanning out from the sun: long soft streaks, additive, slowly breathing
  private rays() {
    const c = document.createElement('canvas')
    c.width = 16
    c.height = 256
    const g = c.getContext('2d')!
    const grad = g.createLinearGradient(0, 0, 0, 256)
    grad.addColorStop(0, 'rgba(255,226,206,0)')
    grad.addColorStop(0.5, 'rgba(255,226,206,0.9)')
    grad.addColorStop(1, 'rgba(255,226,206,0)')
    g.fillStyle = grad
    g.fillRect(0, 0, 16, 256)
    const tex = this.own(new THREE.CanvasTexture(c))
    for (let i = 0; i < 7; i++) {
      const m = this.own(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, fog: false, blending: THREE.AdditiveBlending, opacity: 0.1, rotation: (i - 3) * 0.32 }))
      const sp = new THREE.Sprite(m)
      sp.position.set(160, 70, -620)
      sp.scale.set(70 + (i % 3) * 40, 980, 1)
      sp.userData = { base: 0.035 + (i % 3) * 0.015, p: i * 1.3 }
      this.rays_.push(sp)
      this.scene.add(sp)
    }
  }

  // cherry trees (mai anh đào) along the shores of the lakes and in the town: soft pink clouds on slim trunks
  private blossoms() {
    const L = landscape()
    const crown = this.own(new THREE.IcosahedronGeometry(0.42, 1))
    crown.scale(1, 0.8, 1)
    crown.translate(0, 0.78, 0)
    const trunk = this.own(new THREE.CylinderGeometry(0.035, 0.05, 0.55, 5))
    trunk.translate(0, 0.27, 0)
    const n = L.blossomTone.length
    const crowns = new THREE.InstancedMesh(crown, this.own(new THREE.MeshStandardMaterial({ roughness: 0.8, flatShading: true, emissive: '#ff9fbd', emissiveIntensity: 0.25 })), n)
    const trunks = new THREE.InstancedMesh(trunk, this.own(new THREE.MeshStandardMaterial({ color: '#7a4a5f', roughness: 0.9 })), n)
    place(crowns, L.blossoms, L.blossomTone, BLOSSOM_TONES, 0.03, true)
    place(trunks, L.blossoms, L.blossomTone, ['#7a4a5f'], 0.03, true)
    crowns.castShadow = true
    this.scene.add(crowns, trunks)
  }

  // blossom petals drifting down on a light wind, over the valley
  private petals() {
    const c = document.createElement('canvas')
    c.width = c.height = 64
    const g = c.getContext('2d')!
    const grad = g.createRadialGradient(32, 32, 0, 32, 32, 30)
    grad.addColorStop(0, 'rgba(255,214,228,1)')
    grad.addColorStop(0.6, 'rgba(255,170,200,0.9)')
    grad.addColorStop(1, 'rgba(255,170,200,0)')
    g.fillStyle = grad
    g.beginPath()
    g.ellipse(32, 32, 14, 26, 0.5, 0, Math.PI * 2)
    g.fill()
    const tex = this.own(new THREE.CanvasTexture(c))
    const n = 520
    this.petalBase = new Float32Array(n * 4)
    for (let i = 0; i < n; i++) {
      this.petalBase.set([(Math.random() * 2 - 1) * 110, Math.random() * 46, (Math.random() * 2 - 1) * 90, Math.random() * 6.28], i * 4)
    }
    const geo = this.own(new THREE.BufferGeometry())
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3))
    this.petalMat = this.own(new THREE.PointsMaterial({ map: tex, size: 1.25, sizeAttenuation: true, transparent: true, opacity: 0.9, depthWrite: false, color: '#ffffff' }))
    this.petalPts = new THREE.Points(geo, this.petalMat)
    this.petalPts.frustumCulled = false
    this.scene.add(this.petalPts)
    this.driftPetals(0)
  }

  private driftPetals(t: number) {
    const a = this.petalBase, pos = this.petalPts.geometry.attributes.position as THREE.BufferAttribute
    const ox = this.pivot.x, oz = this.pivot.z
    for (let i = 0; i < a.length / 4; i++) {
      const x0 = a[i * 4], y0 = a[i * 4 + 1], z0 = a[i * 4 + 2], ph = a[i * 4 + 3]
      const fall = (y0 + 46 - t * (1.1 + (ph % 1) * 0.9)) % 46
      pos.setXYZ(i, ox + ((x0 + 110 + t * 0.5) % 220) - 110 + Math.sin(t * 0.5 + ph) * 3, fall + 1, oz + z0 + Math.cos(t * 0.37 + ph * 2) * 2.4)
    }
    pos.needsUpdate = true
  }

  // fireflies over the lakes: tiny warm lights that breathe
  private fireflies() {
    const pts: number[] = []
    for (const lake of landscape().lakes) {
      const w = lake.box[1] - lake.box[0], d = lake.box[3] - lake.box[2]
      const n = Math.min(40, Math.round((w + d) * 2))
      for (let i = 0; i < n; i++) pts.push(lake.box[0] + Math.random() * w, lake.level + 0.6 + Math.random() * 2.2, lake.box[2] + Math.random() * d)
    }
    const geo = this.own(new THREE.BufferGeometry())
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    const tex = this.own(radialTexture([[0, 'rgba(255,240,200,1)'], [0.3, 'rgba(255,214,150,0.8)'], [1, 'rgba(255,200,140,0)']]))
    this.flyMat = this.own(new THREE.PointsMaterial({ map: tex, size: 0.9, sizeAttenuation: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }))
    this.flyPts = new THREE.Points(geo, this.flyMat)
    this.scene.add(this.flyPts)
  }

  // DOM labels that follow a postcard or an area on screen; the page owns the elements
  bindLabels(kind: 'five' | 'area', els: HTMLElement[], areas: ScenePlace[] = []) {
    this.labels = this.labels.filter((l) => l.kind !== kind)
    els.forEach((el, i) => {
      if (!el) return
      if (kind === 'five') this.labels.push({ el, at: this.cardTops[i], kind, i })
      else {
        const [x, z] = toXZ(areas[i].lat, areas[i].lng)
        this.labels.push({ el, at: new THREE.Vector3(x, groundAt(x, z) + 2, z), kind, i })
      }
    })
    this.kick()
  }

  set(next: Partial<SceneState>) {
    // scrolling on to another view of the story hands the camera back to it
    if (next.cam !== undefined && Math.abs(next.cam - this.state.cam) > 1e-4 && !this.turn.drag && this.turned) this.resetTurn()
    Object.assign(this.state, next)
    this.kick()
  }

  // turning the view: the page forwards pointer drags (pixels) and button presses (radians)
  dragStart() {
    this.turn.drag = true
    this.turn.vel = 0
    this.turn.swing = -1
    this.onTurn?.()
  }

  dragBy(dxPx: number, dyPx: number) {
    const t = this.turn
    const dy = (dxPx / this.size.w) * Math.PI * 2.4
    t.yawT += dy
    t.yaw += dy // follow the hand 1:1 while it is down
    t.vel = dy
    t.pitchT = Math.min(0.75, Math.max(-0.28, t.pitchT + (dyPx / this.size.h) * 1.4))
    this.kick()
  }

  dragEnd() {
    this.turn.drag = false
    this.kick()
  }

  turnBy(dyaw: number) {
    this.turn.swing = -1
    this.turn.yawT += dyaw
    this.onTurn?.()
    this.kick()
  }

  // back to the story's own view, by the shortest way round
  resetTurn() {
    const t = this.turn
    t.yawT = Math.round(t.yawT / (Math.PI * 2)) * Math.PI * 2
    t.pitchT = 0
    t.vel = 0
    this.kick()
  }

  // one slow sway to the left and right that shows the model can be turned
  hintTurn() {
    if (this.still || this.turn.drag) return
    this.turn.swing = 0
    this.kick()
  }

  get turned() {
    return Math.abs(this.turn.yawT) > 0.02 || Math.abs(this.turn.pitchT) > 0.02
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
    let moving = false
    // ease toward the scrubbed state at the same speed whatever the frame rate
    const k = this.still ? 1 : 1 - Math.exp(-dt * 6)
    for (const key of Object.keys(this.state) as (keyof SceneState)[]) {
      const d = this.state[key] - this.shown[key]
      if (Math.abs(d) > 0.0005) moving = true
      this.shown[key] = Math.abs(d) < 0.0005 ? this.state[key] : this.shown[key] + d * k
    }
    const tn = this.turn
    if (tn.swing >= 0) {
      tn.swing += dt / 3.4
      if (tn.swing >= 1) tn.swing = -1
      moving = true
    }
    if (!tn.drag) {
      if (Math.abs(tn.vel) > 0.0004) { tn.yawT += tn.vel * dt * 24; tn.vel *= Math.exp(-dt * 3.2); moving = true } else tn.vel = 0
      const kt = this.still ? 1 : 1 - Math.exp(-dt * 5)
      if (Math.abs(tn.yawT - tn.yaw) > 0.0005 || Math.abs(tn.pitchT - tn.pitch) > 0.0005) moving = true
      tn.yaw += (tn.yawT - tn.yaw) * kt
      tn.pitch += (tn.pitchT - tn.pitch) * kt
    } else tn.pitch += (tn.pitchT - tn.pitch) * 0.35
    this.pointerShown.lerp(this.pointer, this.still ? 1 : 1 - Math.exp(-dt * 4))
    if (this.pointerShown.distanceTo(this.pointer) > 0.001) moving = true
    this.apply(t)
    this.renderer.render(this.scene, this.camera)
    this.project()
    this.govern(now)
    if (this.onReady) { const f = this.onReady; this.onReady = null; f() }
    // idle drift (mist, the glow under the postcards) keeps a slow loop alive; still mode draws on change only
    if (this.running && (!this.still || moving)) this.raf = requestAnimationFrame(this.frame)
    else { this.last = 0; this.prevFrame = 0 }
  }

  // Quality governor: the model is meant to run at the display's speed. When frames take much longer than 28 ms for
  // a good while (after a warm-up), drop the costliest extras one step at a time and never bring them back.
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
    if (++g.calm < 40 || g.level >= 3) return
    g.calm = 0
    g.level++
    g.ema = 16
    if (g.level === 1 && this.dpr > 1) {
      this.dpr = 1
      this.renderer.setPixelRatio(1)
      this.renderer.setSize(this.size.w, this.size.h, false)
    } else if (g.level === 2) {
      this.fx = false
      this.petalPts.visible = this.flyPts.visible = false
      this.rays_.forEach((r) => (r.visible = false))
    } else if (g.level === 3 && this.treeMesh) this.treeMesh.count = Math.floor(this.treeFull / 2)
  }

  get quality() {
    return this.slow.level
  }

  private apply(t: number) {
    const s = this.shown
    const i = Math.min(this.keys.length - 2, Math.floor(s.cam))
    const f = s.cam - i
    const e = f * f * (3 - 2 * f)
    const a = this.keys[i], b = this.keys[i + 1]
    this.camera.position.lerpVectors(a.pos, b.pos, e)
    this.look.lerpVectors(a.look, b.look, e)
    this.pivot.lerpVectors(a.pivot, b.pivot, e)
    // keys are framed for a 16:10 window; step back on narrower ones so the scene still fits
    const fit = Math.min(1.45, Math.max(1, 1.6 / this.camera.aspect))
    this.camera.position.sub(this.look).multiplyScalar(fit).add(this.look)
    // a slow breath in the hero and a little give under the pointer, like looking out of a plane window
    const breathe = this.still ? 0 : Math.sin(t * 0.25) * 1.2 * (1 - Math.min(1, s.cam))
    this.camera.position.x += this.pointerShown.x * 6 + breathe
    this.camera.position.y += this.pointerShown.y * 3
    this.turnRig()
    this.camera.lookAt(this.look)
    const { w, h } = this.size
    this.camera.setViewOffset(w, h, -s.shift * w, 0, w, h)
    this.camera.updateProjectionMatrix()

    // lights fade in on load, then dim to faint grey when the five are chosen
    this.lightMat.opacity = (this.still ? 1 : Math.min(1, t / 1.6)) * (0.18 + 0.82 * s.dots)
    this.lightMat.color.set(C.sun).lerp(this.grey, 1 - s.dots)
    this.cards.forEach(({ group, ring }, n) => {
      const r = clamp01(s.five * 1.6 - n * 0.15)
      const k = 1 - Math.pow(1 - r, 3)
      group.scale.setScalar(k || 0.0001)
      group.visible = r > 0
      group.position.y = ring.position.y - 0.08 + (this.still ? 0 : Math.sin(t * 0.9 + n) * 0.25)
      const pulse = this.still ? 0.5 : (Math.sin(t * 2.2 - n) + 1) / 2
      ;(ring.material as THREE.MeshBasicMaterial).opacity = r * (0.25 + 0.4 * pulse)
      ring.scale.setScalar(1 + pulse * 0.4)
    })
    this.dashes.count = Math.floor(s.route * this.dashCount)
    this.rider.visible = s.travel > 0.002
    if (this.rider.visible) this.rider.position.copy(this.routeCurve.getPointAt(clamp01(s.travel))).add(this.tmp.set(0, 0.6, 0))
    if (!this.still && this.fx) {
      this.driftPetals(t)
      this.rays_.forEach((r) => { const u = r.userData as { base: number; p: number }; (r.material as THREE.SpriteMaterial).opacity = u.base * (0.75 + 0.25 * Math.sin(t * 0.35 + u.p)) })
    }
    if (this.fx) this.flyMat.opacity = this.still ? 0.8 : 0.55 + 0.45 * Math.sin(t * 1.3)
    this.mist.forEach((c) => {
      const u = c.userData as { x: number; s: number; p: number }
      if (!this.still) c.position.x = u.x + Math.sin(t * 0.04 * u.s + u.p) * 14
      ;(c.material as THREE.SpriteMaterial).opacity = 0.34 + 0.4 * s.areas
    })
  }

  // the visitor's turn: the camera and its target swing round the pivot; pitch lifts or lowers the camera on that circle
  private turnRig() {
    const tn = this.turn
    const sway = tn.swing >= 0 ? Math.sin(tn.swing * Math.PI * 2) * 0.55 * Math.sin(tn.swing * Math.PI) : 0
    const yaw = tn.yaw + sway
    const pv = this.pivot, cam = this.camera.position, look = this.look
    if (Math.abs(yaw) > 1e-5) {
      const c = Math.cos(yaw), s = Math.sin(yaw)
      for (const v of [cam, look]) {
        const x = v.x - pv.x, z = v.z - pv.z
        v.x = pv.x + x * c + z * s
        v.z = pv.z - x * s + z * c
      }
    }
    if (Math.abs(tn.pitch) > 1e-4) {
      const ox = cam.x - pv.x, oy = cam.y - pv.y, oz = cam.z - pv.z
      const h = Math.hypot(ox, oz) || 1, len = Math.hypot(h, oy)
      const ang = Math.min(1.3, Math.max(0.05, Math.atan2(oy, h) + tn.pitch))
      cam.set(pv.x + (ox / h) * Math.cos(ang) * len, pv.y + Math.sin(ang) * len, pv.z + (oz / h) * Math.cos(ang) * len)
    }
    // never under the ground, whichever way the visitor turns
    cam.y = Math.max(cam.y, groundAt(cam.x, cam.z) + 5)
  }

  private project() {
    const { w, h } = this.size
    for (const l of this.labels) {
      if (l.kind === 'five') {
        const g = this.cards[l.i].group
        this.tmp.set(g.position.x, g.position.y + (STEM + CARD.h) * g.scale.y + 0.6, g.position.z)
      } else this.tmp.copy(l.at)
      this.tmp.project(this.camera)
      const vis = l.kind === 'five' ? clamp01(this.shown.five * 1.6 - l.i * 0.15 - 0.4) : this.shown.areas
      const sx = ((this.tmp.x + 1) / 2) * w
      // labels never sit under the text column or half off the edge
      const hidden = this.tmp.z > 1 || sx < w * (this.shown.shift + 0.24) || sx > w - 80
      l.el.style.transform = `translate3d(${sx}px, ${((1 - this.tmp.y) / 2) * h}px, 0)`
      l.el.style.opacity = hidden ? '0' : String(vis)
    }
  }

  dispose() {
    this.running = false
    cancelAnimationFrame(this.raf)
    this.disposables.forEach((d) => d.dispose())
    this.renderer.dispose()
  }
}

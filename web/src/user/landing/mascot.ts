import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

// The TripGuardian cloud (the logo, web/public/img/brand/mark.webp) as a small toon figure for the landing's 3D scene
// (docs/UI_SPEC_LANDING.md §2), flying in front of the journey map. Built from code only: puffs of spheres under a toon
// material, a terracotta line drawn by an inverted hull, a bucket hat, two hands holding a folded map. Every motion is
// procedural (sines, easing, a squash spring), never a skeleton. The scene decides where the figure flies; the figure only holds its pose.
// Origin at the soles of the feet, about 1.65 units tall, facing +z. Two stubby legs carry it: they dangle while it
// flies and walk, plant and take its weight once the scene puts it on the map (`setGround`).

export type MascotAct = 'hover' | 'listen' | 'pick' | 'walk' | 'stamp' | 'wave'

const INK = '#2b2720' // eyes and mouth: the buttons' brown
const PAPER = '#fbf3e4'
const LINE = 0.024 // outline thickness

// sphere puffs of the cloud body: x, y, z, radius
const PUFFS: [number, number, number, number][] = [
  [0, 0.5, 0, 0.42],
  [0, 0.29, 0.04, 0.3],
  [-0.3, 0.32, 0.02, 0.27],
  [0.3, 0.32, 0.02, 0.27],
  [-0.37, 0.62, 0, 0.25],
  [0.37, 0.62, 0, 0.25],
  [-0.17, 0.86, 0, 0.27],
  [0.18, 0.88, 0, 0.28],
]
const LEG = 0.3 // how far the body's underside floats above the soles
const HIP = 0.38 // hip joint to sole, at rest
const HEIGHT = 1.35 + LEG
// walking gait (designed with sol 6.1): the cycle is locked to the distance walked, so planted feet never slide
const GAIT = { cycle: 0.4, stance: 0.6, lift: 0.075, splay: 0.055, hipX: 0.14, shoeR: 0.09, shoeY: 0.62, shoeZ: 1.55, maxCadence: 2.4 }
const SHAFT = HIP - GAIT.shoeR * GAIT.shoeY // hip joint to the shoe's centre
const HINGE = new THREE.Vector3(0, 0.4, 0.5) // where the map folds, in front of the body
const HALF = { w: 0.3, h: 0.34 }

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x))
const s01 = (x: number) => clamp(x, 0, 1)
const smooth01 = (x: number) => { const y = s01(x); return y * y * (3 - 2 * y) }
const clamp01s = smooth01
const ease = (cur: number, target: number, rate: number, dt: number) => cur + (target - cur) * (1 - Math.exp(-dt * rate))

// a geometry painted one colour (vertex colours), non-indexed so any mix of shapes can be merged
function paint(g: THREE.BufferGeometry, hex: string) {
  const out = g.index ? g.toNonIndexed() : g
  if (out !== g) g.dispose()
  const c = new THREE.Color(hex)
  const n = out.attributes.position.count
  const col = new Float32Array(n * 3)
  for (let i = 0; i < n; i++) col.set([c.r, c.g, c.b], i * 3)
  out.setAttribute('color', new THREE.BufferAttribute(col, 3))
  return out
}

const plain = (g: THREE.BufferGeometry) => {
  const out = g.index ? g.toNonIndexed() : g
  if (out !== g) g.dispose()
  out.deleteAttribute('uv')
  return out
}

function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  draw(c.getContext('2d')!)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

// the map the cloud holds: cream paper, a dotted route, a pin; `stamped` adds the "Đúng gu" mark of the last station
function mapTexture(brand: string, stamped: boolean) {
  return canvasTexture(256, 144, (g) => {
    g.fillStyle = PAPER
    g.fillRect(0, 0, 256, 144)
    g.strokeStyle = brand
    g.lineWidth = 6
    g.strokeRect(3, 3, 250, 138)
    g.lineWidth = 2
    g.globalAlpha = 0.35
    g.beginPath(); g.moveTo(128, 6); g.lineTo(128, 138); g.stroke() // the fold
    g.beginPath(); g.moveTo(66, 6); g.lineTo(80, 138); g.moveTo(190, 6); g.lineTo(176, 138); g.stroke()
    g.globalAlpha = 1
    g.setLineDash([7, 8])
    g.lineWidth = 5
    g.lineCap = 'round'
    g.beginPath(); g.moveTo(26, 116); g.bezierCurveTo(70, 40, 120, 128, 168, 70); g.stroke()
    g.setLineDash([])
    g.fillStyle = brand
    g.beginPath(); g.arc(186, 46, 13, Math.PI * 0.85, Math.PI * 2.15); g.lineTo(186, 78); g.closePath(); g.fill() // the pin
    g.fillStyle = PAPER
    g.beginPath(); g.arc(186, 46, 5, 0, Math.PI * 2); g.fill()
    if (stamped) {
      g.save()
      g.translate(196, 104)
      g.rotate(-0.22)
      g.strokeStyle = brand
      g.fillStyle = brand
      g.lineWidth = 4
      g.beginPath(); g.arc(0, 0, 30, 0, Math.PI * 2); g.stroke()
      g.lineWidth = 1.5
      g.beginPath(); g.arc(0, 0, 24, 0, Math.PI * 2); g.stroke()
      g.font = '700 15px "Be Vietnam Pro", system-ui, sans-serif'
      g.textAlign = 'center'
      g.textBaseline = 'middle'
      g.fillText('Đúng', 0, -6)
      g.fillText('gu', 0, 10)
      g.restore()
    }
  })
}

// the "…" speech bubble of the chatbot logo
function bubbleTexture(brand: string) {
  return canvasTexture(160, 128, (g) => {
    g.fillStyle = '#ffffff'
    g.strokeStyle = brand
    g.lineWidth = 7
    g.beginPath()
    g.roundRect(8, 8, 144, 86, 26)
    g.moveTo(40, 92); g.lineTo(26, 120); g.lineTo(66, 93)
    g.fill()
    g.stroke()
    g.fillStyle = '#ffffff'
    g.fillRect(40, 86, 24, 10) // the tail joins the bubble without a line across it
    g.fillStyle = brand
    for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(50 + i * 30, 51, 9, 0, Math.PI * 2); g.fill() }
  })
}

// a small plane, the decal on the hat
function planeShape() {
  const s = new THREE.Shape()
  s.moveTo(0, 1)
  s.lineTo(0.14, 0.3); s.lineTo(1, -0.1); s.lineTo(1, -0.3); s.lineTo(0.14, -0.1)
  s.lineTo(0.1, -0.7); s.lineTo(0.4, -0.95); s.lineTo(0.4, -1.08); s.lineTo(0, -0.98)
  s.lineTo(-0.4, -1.08); s.lineTo(-0.4, -0.95); s.lineTo(-0.1, -0.7)
  s.lineTo(-0.14, -0.1); s.lineTo(-1, -0.3); s.lineTo(-1, -0.1); s.lineTo(-0.14, 0.3)
  s.closePath()
  return new THREE.ShapeGeometry(s)
}

export class Mascot {
  readonly root = new THREE.Group()
  readonly height = HEIGHT
  private rig = new THREE.Group() // body and legs, tilted as one toward the camera
  private body = new THREE.Group() // everything that bobs, leans and squashes
  private legs: { shaft: THREE.Group; shoe: THREE.Group; shadow: THREE.Mesh }[] = []
  private shadow: THREE.Mesh
  private shadowMat: THREE.MeshBasicMaterial
  private footMat: THREE.MeshBasicMaterial
  private phase = 0 // gait phase in cycles, advanced by distance walked
  private routeLen = 100 // world length of the route that `k` runs along
  grounded = false // on the map, standing on its feet (set by the scene)
  private tilt = 0
  private eyes: THREE.Mesh
  private hands: THREE.Mesh[] = []
  private halves: THREE.Group[] = []
  private headset: THREE.Mesh
  private bubble: THREE.Sprite
  private stampTool: THREE.Mesh
  private mapMat: THREE.MeshToonMaterial
  private maps: THREE.Texture[]
  private own: { dispose(): void }[] = []
  private t = Math.random() * 10
  private act: MascotAct = 'hover'
  private k = 0
  private look: THREE.Vector3 | null = null
  private lookLocal = new THREE.Vector3()
  private tmp = new THREE.Vector3()
  private hinge = new THREE.Vector3()
  // the pose, eased toward what the act asks for
  private p = { open: 0, raise: 0, headset: 0, bubble: 0, stamp: 0, wave: 0, sit: 0, stride: 0, yaw: 0, pitch: 0, lean: 0, float: 1, read: 0, ground: 0 }
  private prevK = 0
  private blink = { next: 2 + Math.random() * 2, left: 0 }
  private squash = { x: 0, v: 0 }
  private air = 0

  constructor(brand: string) {
    const soft = '#f4c9ae'
    const ramp = new THREE.DataTexture(new Uint8Array([150, 150, 150, 255, 215, 215, 215, 255, 255, 255, 255, 255]), 3, 1, THREE.RGBAFormat)
    ramp.minFilter = ramp.magFilter = THREE.NearestFilter
    ramp.needsUpdate = true
    const toon = this.keep(new THREE.MeshToonMaterial({ vertexColors: true, gradientMap: ramp }))
    const line = this.keep(new THREE.MeshBasicMaterial({ color: brand, side: THREE.BackSide }))
    this.keep(ramp)

    // hat: a dome on a brim with a terracotta band and the plane decal, tipped to one side
    const hatAt = new THREE.Matrix4().compose(new THREE.Vector3(0.05, 1.0, 0.02), new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.12, 0, -0.2)), new THREE.Vector3(1, 1, 1))
    const dome = (r: number) => new THREE.SphereGeometry(r, 16, 6, 0, Math.PI * 2, 0, Math.PI / 2)
    const brim = (r: number, h: number) => new THREE.CylinderGeometry(r, r, h, 22)
    const band = new THREE.CylinderGeometry(0.302, 0.302, 0.07, 18, 1, true)
    band.translate(0, 0.04, 0)
    const decal = planeShape()
    decal.scale(0.07, 0.07, 1)
    decal.rotateZ(-0.6)
    decal.rotateX(-0.6) // lie on the dome, which slopes back here
    decal.translate(0, 0.17, 0.252)
    const hat = [paint(dome(0.3), '#ffffff'), paint(brim(0.44, 0.03), '#ffffff'), paint(band, brand), paint(decal, brand)].map((g) => g.applyMatrix4(hatAt))
    const hatLine = [plain(dome(0.3 + LINE)), plain(brim(0.44 + LINE, 0.03 + LINE * 2))].map((g) => g.applyMatrix4(hatAt))

    // face: smile and cheeks ride with the body; the eyes are their own mesh so they can blink and look
    const smile = new THREE.TorusGeometry(0.07, 0.017, 6, 14, Math.PI)
    smile.rotateZ(Math.PI)
    smile.rotateX(-0.25)
    smile.translate(0, 0.6, 0.405)
    const cheek = (x: number) => { const g = new THREE.SphereGeometry(0.06, 10, 6); g.scale(1, 0.75, 0.35); g.translate(x, 0.575, 0.37); return paint(g, soft) }
    const puffs = PUFFS.map(([x, y, z, r]) => { const g = new THREE.SphereGeometry(r, 16, 11); g.translate(x, y, z); return g })
    const bodyGeo = this.keep(mergeGeometries([...puffs.map((g) => paint(g, '#ffffff')), ...hat, paint(smile, INK), cheek(-0.21), cheek(0.21)]))
    const hullGeo = this.keep(mergeGeometries([...PUFFS.map(([x, y, z, r]) => { const g = new THREE.SphereGeometry(r + LINE, 16, 11); g.translate(x, y, z); return plain(g) }), ...hatLine]))
    this.body.add(new THREE.Mesh(bodyGeo, toon), new THREE.Mesh(hullGeo, line))

    const eye = (x: number) => { const g = new THREE.CapsuleGeometry(0.034, 0.06, 4, 8); g.translate(x, 0, 0); return paint(g, INK) }
    this.eyes = new THREE.Mesh(this.keep(mergeGeometries([eye(-0.11), eye(0.11)])), toon)
    this.eyes.position.set(0, 0.69, 0.355)
    this.body.add(this.eyes)

    // hands: a white ball with its own outline (two draw groups)
    const handGeo = this.keep(mergeGeometries([paint(new THREE.SphereGeometry(0.095, 12, 8), '#ffffff'), paint(new THREE.SphereGeometry(0.095 + LINE, 12, 8), brand)], true))
    for (let i = 0; i < 2; i++) {
      const h = new THREE.Mesh(handGeo, [toon, line])
      this.hands.push(h)
      this.body.add(h)
    }

    // the map: two halves hinged at the middle, each showing its half of one texture
    this.maps = [mapTexture(brand, false), mapTexture(brand, true)].map((t) => this.keep(t))
    this.mapMat = this.keep(new THREE.MeshToonMaterial({ map: this.maps[0], gradientMap: ramp, side: THREE.DoubleSide }))
    for (const side of [-1, 1]) {
      const g = new THREE.PlaneGeometry(HALF.w, HALF.h)
      g.translate((side * HALF.w) / 2, 0, 0)
      const uv = g.attributes.uv as THREE.BufferAttribute
      for (let i = 0; i < uv.count; i++) uv.setX(i, side < 0 ? uv.getX(i) * 0.5 : 0.5 + uv.getX(i) * 0.5)
      const pivot = new THREE.Group()
      pivot.add(new THREE.Mesh(this.keep(g), this.mapMat))
      this.halves.push(pivot)
      this.body.add(pivot)
    }

    // headset of the chatbot logo: a band over the hat and two ear cups (only while listening)
    const arc = new THREE.TorusGeometry(0.6, 0.028, 6, 22, Math.PI)
    const cup = (x: number) => { const g = new THREE.CylinderGeometry(0.11, 0.11, 0.09, 14); g.rotateZ(Math.PI / 2); g.translate(x, 0, 0); return g }
    const mic = new THREE.CylinderGeometry(0.018, 0.018, 0.34, 6)
    mic.rotateZ(1.2)
    mic.rotateY(-0.9)
    mic.translate(-0.48, -0.12, 0.16)
    this.headset = new THREE.Mesh(this.keep(mergeGeometries([plain(arc), plain(cup(-0.6)), plain(cup(0.6)), plain(mic)])), this.keep(new THREE.MeshToonMaterial({ color: brand, gradientMap: ramp })))
    this.headset.position.set(0, 0.72, 0)
    this.body.add(this.headset)

    this.bubble = new THREE.Sprite(this.keep(new THREE.SpriteMaterial({ map: this.keep(bubbleTexture(brand)), transparent: true, depthWrite: false })))
    this.bubble.center.set(0.15, 0)
    this.bubble.position.set(0.5, 1.15, 0.2)
    this.body.add(this.bubble)

    // the rubber stamp of the last station: a wooden handle on a terracotta foot
    const knob = new THREE.SphereGeometry(0.05, 10, 6)
    knob.translate(0, 0.17, 0)
    const stem = new THREE.CylinderGeometry(0.025, 0.035, 0.12, 8)
    stem.translate(0, 0.1, 0)
    const foot = new THREE.CylinderGeometry(0.08, 0.08, 0.04, 14)
    this.stampTool = new THREE.Mesh(this.keep(mergeGeometries([paint(knob, '#8a5a3b'), paint(stem, '#a87450'), paint(foot, brand)])), toon)
    this.body.add(this.stampTool)

    // legs: a white shaft from the hip (inside the body) to a brown shoe, outlined like the rest. The shoe is its own
    // object so the shaft can stretch without squashing it; both live under the rig, not the bobbing body.
    const SHOE = '#8a5a3b'
    const shaft = (r: number) => { const g = new THREE.CapsuleGeometry(r, Math.max(0.01, SHAFT - 2 * 0.065), 4, 8); g.translate(0, -SHAFT / 2, 0); return g }
    const shoe = (r: number) => { const g = new THREE.SphereGeometry(r, 12, 8); g.scale(1, GAIT.shoeY, GAIT.shoeZ); return g }
    const shaftGeo = this.keep(paint(shaft(0.065), '#ffffff'))
    const shaftHull = this.keep(plain(shaft(0.065 + LINE)))
    const shoeGeo = this.keep(paint(shoe(GAIT.shoeR), SHOE))
    const shoeHull = this.keep(plain(shoe(GAIT.shoeR + LINE)))
    this.footMat = this.keep(new THREE.MeshBasicMaterial({ color: '#4a2f1a', transparent: true, opacity: 0, depthWrite: false }))
    const footGeo = this.keep(new THREE.CircleGeometry(0.1, 16).rotateX(-Math.PI / 2).scale(1, 1, 1.6))
    for (let i = 0; i < 2; i++) {
      const sh = new THREE.Group()
      sh.add(new THREE.Mesh(shaftGeo, toon), new THREE.Mesh(shaftHull, line))
      const foot = new THREE.Group()
      foot.add(new THREE.Mesh(shoeGeo, toon), new THREE.Mesh(shoeHull, line))
      const spot = new THREE.Mesh(footGeo, this.footMat)
      spot.renderOrder = 2
      this.legs.push({ shaft: sh, shoe: foot, shadow: spot })
      this.rig.add(sh, foot)
      this.root.add(spot)
    }
    // a soft patch under the body, only once it stands on the map
    this.shadowMat = this.keep(new THREE.MeshBasicMaterial({ color: '#6b4426', transparent: true, opacity: 0, depthWrite: false }))
    this.shadow = new THREE.Mesh(this.keep(new THREE.CircleGeometry(0.46, 24).rotateX(-Math.PI / 2)), this.shadowMat)
    this.shadow.position.y = 0.01
    this.shadow.renderOrder = 1

    this.rig.add(this.body)
    this.root.add(this.rig, this.shadow)
    // like the postcards, the figure stays clear of the valley's haze
    this.root.traverse((o) => {
      o.castShadow = o.receiveShadow = false
      const mats = (o as THREE.Mesh).material
      for (const m of Array.isArray(mats) ? mats : mats ? [mats] : []) (m as THREE.Material & { fog?: boolean }).fog = false
    })
    this.pose()
  }

  private keep<T extends { dispose(): void }>(x: T) {
    this.own.push(x)
    return x
  }

  // what the figure is doing, and how far into it (open the map, pop the bubble, press the stamp…)
  set(act: MascotAct, k: number) {
    this.act = act
    this.k = clamp(k, 0, 1)
  }

  // eyes and head turn toward a point in the world (the pointer, a postcard); null = straight ahead
  lookAt(target: THREE.Vector3 | null) {
    this.look = target ? (this.look ?? new THREE.Vector3()).copy(target) : null
  }

  // world length of the route that the figure's `k` (0..1) runs along while it walks
  setRoute(length: number) {
    this.routeLen = length
  }

  // true once the scene puts the figure on the map: the legs take its weight, it stops bobbing in the air
  setGround(on: boolean) {
    this.grounded = on
  }

  // lean the whole figure back toward a camera that looks down on it (radians)
  setTilt(a: number) {
    this.tilt = a
  }

  // 0..1 share of a jump: stretches in the air, squashes on landing
  setAir(a: number) {
    if (this.air > 0.15 && a < 0.02) this.squash.v -= 3.2
    this.air = a
  }

  update(dt: number) {
    this.t += dt
    const p = this.p, k = this.k, a = this.act
    const want = {
      open: a === 'listen' ? 0.35 : a === 'walk' ? 0.8 : 1,
      raise: a === 'pick' ? k : a === 'walk' ? 0.5 : 0,
      headset: a === 'listen' ? 1 : 0,
      bubble: a === 'listen' ? k : 0,
      stamp: a === 'stamp' ? k : a === 'wave' ? 1 : 0,
      wave: a === 'wave' ? 1 : 0,
      sit: a === 'stamp' || a === 'wave' ? 1 : 0,
      float: a === 'hover' || a === 'listen' ? 1 : 0,
      read: a === 'walk' ? 1 : 0,
    }
    // walking: the gait phase advances with the distance covered (in the figure's own units), so feet stay planted;
    // a very fast scroll is capped at a brisk cadence rather than a blur of legs
    const walked = a === 'walk' && dt > 0 && dt < 0.2 ? (Math.abs(k - this.prevK) * this.routeLen) / Math.max(0.01, this.root.scale.x) : 0
    this.prevK = k
    const ups = dt > 0 ? walked / dt : 0
    this.phase += Math.min(walked / GAIT.cycle, GAIT.maxCadence * dt)
    p.stride = ease(p.stride, ups < 0.05 ? 0 : clamp(ups / 0.6, 0, 1), 10, dt)
    p.ground = ease(p.ground, this.grounded ? 1 : 0, 7, dt)
    for (const key of Object.keys(want) as (keyof typeof want)[]) p[key] = ease(p[key], want[key], key === 'stamp' ? 14 : 5, dt)

    // where to look, in the figure's own space
    let yaw = 0, pitch = 0
    if (this.look) {
      this.root.updateWorldMatrix(true, false)
      this.lookLocal.copy(this.look)
      this.root.worldToLocal(this.lookLocal)
      yaw = clamp(Math.atan2(this.lookLocal.x, Math.max(0.2, this.lookLocal.z)), -0.6, 0.6)
      pitch = clamp(Math.atan2(this.lookLocal.y - 0.7, Math.hypot(this.lookLocal.x, this.lookLocal.z)), -0.4, 0.4)
    }
    p.yaw = ease(p.yaw, yaw, 4, dt)
    p.pitch = ease(p.pitch, pitch, 4, dt)

    // blink every 3–5 s
    const b = this.blink
    b.next -= dt
    if (b.next <= 0) { b.left = 0.13; b.next = 3 + Math.random() * 2 }
    b.left = Math.max(0, b.left - dt)

    // squash spring (landings), in small steps; a long gap (a still frame) just lets it rest
    const s = this.squash
    if (dt > 0.2) s.x = s.v = 0
    else for (let i = 0, n = Math.ceil(dt * 120), h = dt / Math.max(1, n); i < n; i++) { s.v += (-80 * s.x - 9 * s.v) * h; s.x += s.v * h }
    if (Math.abs(s.x) < 1e-4 && Math.abs(s.v) < 1e-3) s.x = s.v = 0

    this.pose()
  }

  private pose() {
    const p = this.p, t = this.t
    const fract = (x: number) => x - Math.floor(x)
    const ph = fract(this.phase), tau = Math.PI * 2, a = p.stride
    // each footfall (twice a cycle) a small thud; the body stays fairly steady so the map under it remains readable
    const impact = a * Math.exp(-fract(2 * ph) / 0.075)
    const hop = a * 0.02 * (1 - Math.cos(2 * tau * ph)) * 0.5
    // reading while walking: every 5.5 s the head dips to the map for about 1.3 s, then looks up at the road
    const cyc = ((t % 5.5) + 5.5) % 5.5
    const read = p.read * (1 - clamp01s((cyc - 4.25) / 0.35)) * clamp01s((cyc - 3.3) / 0.35)
    const bob = Math.sin(t * 1.7) * 0.045 * p.float + Math.sin(t * 2.1) * 0.012
    const stretch = this.air * 0.14 - this.squash.x * 0.6 - impact * 0.03
    this.rig.rotation.x = -this.tilt
    this.body.position.y = LEG + bob + hop + 0.06 * p.float - 0.05 * p.sit
    this.body.scale.set(1 - stretch * 0.5 + p.sit * 0.04, 1 + stretch - p.sit * 0.08, 1 - stretch * 0.5)
    this.body.rotation.set(p.pitch * -0.35 + p.stride * 0.08 + read * 0.22, p.yaw * 0.45, Math.sin(t * 0.9) * 0.04 * p.float + Math.sin(tau * ph) * 0.05 * p.stride)
    this.body.position.x = Math.sin(tau * ph) * 0.016 * 1.5 * p.stride
    this.eyes.position.set(p.yaw * 0.06, 0.69 + p.pitch * 0.035 - read * 0.06, 0.355)
    this.eyes.scale.y = this.blink.left > 0 ? 0.12 : 1

    // the map: open by `open`, lifted by `raise`
    const fold = (1 - p.open) * 1.35
    const hinge = this.hinge.copy(HINGE)
    hinge.y += p.raise * 0.42 + read * 0.07 - p.sit * 0.04
    hinge.z += p.raise * 0.06
    this.halves.forEach((h, i) => {
      h.position.copy(hinge)
      h.rotation.set(-p.raise * 0.35, (i ? -1 : 1) * fold, 0)
    })
    // hands at the outer edges of the map; the right one leaves it to press the stamp or to wave
    const edge = (side: number, out: THREE.Vector3) => out.set(hinge.x + side * HALF.w * Math.cos(fold) * 0.96, hinge.y - 0.05, hinge.z + HALF.w * Math.sin(fold) * 0.96 - 0.02)
    edge(-1, this.hands[0].position)
    const right = edge(1, this.hands[1].position)
    const press = p.stamp < 0.5 ? p.stamp * 2 : 1 - (p.stamp - 0.5) * 2 // down then up
    if (p.stamp > 0.01) {
      right.x = THREE.MathUtils.lerp(right.x, hinge.x + 0.16, Math.min(1, p.stamp * 3))
      right.y = hinge.y + 0.32 - press * 0.3
      right.z = hinge.z + 0.12
    }
    if (p.wave > 0.01) {
      right.lerp(this.tmp.set(0.56 + Math.sin(t * 9) * 0.07, 0.95 + Math.cos(t * 9) * 0.03, 0.18), p.wave)
    }
    // legs: hang and sway while it flies; once it stands on the map, a distance-locked gait with planted feet
    const g = p.ground, sit = p.sit
    const hipY = THREE.MathUtils.lerp(this.body.position.y + 0.08, HIP - 0.05 * sit, g)
    const speed = smooth01(a * 3) // the reach settles to a neutral stance when it stops
    this.legs.forEach((leg, i) => {
      const side = i ? 1 : -1
      const gp = this.gait(side, (ph + (i ? 0.5 : 0)) % 1, a, speed, hipY)
      const sway = Math.sin(t * 1.3 + i * 1.9) * 0.16
      const dang = { rx: sway, rz: side * 0.05, sy: 1, px: side * GAIT.hipX, fy: hipY - SHAFT * Math.cos(sway), fz: -SHAFT * Math.sin(sway), pitch: 0, c: 0 }
      const mix = (u: number, v: number) => THREE.MathUtils.lerp(u, v, g)
      leg.shaft.position.set(mix(dang.px, gp.pivotX), hipY, 0)
      leg.shaft.rotation.set(mix(dang.rx, gp.rotationX), 0, mix(dang.rz, gp.rotationZ))
      leg.shaft.scale.y = mix(dang.sy, gp.scaleY)
      leg.shoe.position.set(side * GAIT.hipX, mix(dang.fy, gp.footY), mix(dang.fz, gp.footZ) + 0.02)
      leg.shoe.rotation.x = mix(0, gp.shoePitch)
      leg.shadow.position.set(side * GAIT.hipX, 0.012, gp.footZ + 0.02)
      leg.shadow.scale.setScalar(gp.shadowScale)
      leg.shadow.visible = g > 0.01
    })
    this.footMat.opacity = 0.3 * g
    this.shadowMat.opacity = 0.16 * g
    this.shadow.scale.set(1, 1, 0.85)
    this.stampTool.visible = p.stamp > 0.02 && p.wave < 0.6
    this.stampTool.position.copy(right).add(this.tmp.set(0, -0.2, 0))
    this.mapMat.map = this.maps[(this.act === 'stamp' && this.k > 0.55) || this.act === 'wave' ? 1 : 0]

    this.headset.visible = p.headset > 0.02
    this.headset.scale.setScalar(0.6 + 0.4 * p.headset)
    this.bubble.visible = p.bubble > 0.02
    const pop = p.bubble * (1 + Math.sin(Math.min(1, p.bubble) * Math.PI) * 0.15)
    this.bubble.scale.set(0.5 * pop, 0.4 * pop, 1)

  }

  // one leg of the gait (sol 6.1's design): the foot's z, lift and pitch for a phase (cycles), and the shaft's angle
  // and length that put the shoe there from the hip
  private gait(side: number, q: number, a: number, speed: number, hipY: number) {
    const { cycle, stance, lift: liftMax, splay, shoeR, shoeY, shoeZ } = GAIT
    const reach = (cycle * stance) / 2
    const planted = q < stance
    const u = planted ? q / stance : (q - stance) / (1 - stance)
    let z: number, lift = 0, pitch: number
    if (planted) {
      z = reach * (1 - 2 * u)
      pitch = a * (-0.1 * (1 - smooth01(u / 0.16)) + 0.16 * smooth01((u - 0.78) / 0.22))
    } else {
      // the swing returns along a Hermite curve that meets the stance's speed at both ends
      const m = -cycle * (1 - stance)
      z = -reach * (2 * u ** 3 - 3 * u ** 2 + 1) + m * (u ** 3 - 2 * u ** 2 + u) + reach * (-2 * u ** 3 + 3 * u ** 2) + m * (u ** 3 - u ** 2)
      lift = liftMax * a * Math.sin(Math.PI * u) ** 2
      pitch = a * (0.16 * (1 - smooth01(u / 0.35)) - 0.1 * smooth01((u - 0.65) / 0.35))
    }
    z *= speed
    const support = shoeR * Math.hypot(shoeY * Math.cos(pitch), shoeZ * Math.sin(pitch)) // the pitched shoe still rests on the paper
    const H = hipY - support - lift
    const rz = side * splay
    const vertical = H / Math.cos(rz)
    const length = Math.hypot(vertical, z)
    return {
      pivotX: side * GAIT.hipX - H * Math.tan(rz),
      rotationX: -Math.atan2(z, vertical),
      rotationZ: rz,
      scaleY: length / SHAFT,
      footY: support + lift,
      footZ: z,
      shoePitch: pitch,
      shadowScale: 1 + 2 * lift,
    }
  }

  dispose() {
    this.own.forEach((d) => d.dispose())
    this.own = []
  }
}

import * as T from 'three'

// The tabletop Đà Lạt miniature, ported from TripGuardian-3D-Source/scene.html.
// Fictional stylised scenery, not a map. Built imperatively (as in the source)
// and driven by update(choose, time):
//   choose 0..1/3   five saved places float apart
//   choose 1/3..2/3 three that fit settle together, two drift away
//   choose 2/3..1   the orange thread draws between the chosen three

export interface Miniature {
  group: T.Group
  update: (choose: number, time: number) => void
  dispose: () => void
}

const smooth = (x: number) => {
  x = T.MathUtils.clamp(x, 0, 1)
  return x * x * (3 - 2 * x)
}

export function buildMiniature(): Miniature {
  const root = new T.Group()
  const geos: T.BufferGeometry[] = []
  const mats: T.Material[] = []

  const mat = (c: string, roughness = 0.8, metalness = 0) => {
    const m = new T.MeshStandardMaterial({ color: c, roughness, metalness })
    mats.push(m)
    return m
  }
  const C = {
    paper: mat('#eadfc9'),
    edge: mat('#c4ac88'),
    dark: mat('#224f40'),
    pine: mat('#35644d'),
    light: mat('#60876a'),
    wood: mat('#976744'),
    terra: mat('#c86c43'),
    orange: mat('#e88747', 0.42, 0.15),
    water: mat('#5b9b9b', 0.32, 0.16),
    white: mat('#f8edd8'),
    gold: mat('#bda472', 0.35, 0.4),
  }

  const mesh = (g: T.BufferGeometry, m: T.Material, p: T.Object3D, x = 0, y = 0, z = 0) => {
    geos.push(g)
    const o = new T.Mesh(g, m)
    o.position.set(x, y, z)
    o.castShadow = true
    o.receiveShadow = true
    p.add(o)
    return o
  }
  const box = (p: T.Object3D, w: number, h: number, d: number, m: T.Material, x: number, y: number, z: number) =>
    mesh(new T.BoxGeometry(w, h, d), m, p, x, y, z)
  const cylinder = (p: T.Object3D, r1: number, r2: number, h: number, m: T.Material, x: number, y: number, z: number, n = 32) =>
    mesh(new T.CylinderGeometry(r1, r2, h, n), m, p, x, y, z)
  const tube = (p: T.Object3D, pts: number[][], r: number, m: T.Material) => {
    const curve = new T.CatmullRomCurve3(pts.map(([x, y, z]) => new T.Vector3(x, y, z)))
    return mesh(new T.TubeGeometry(curve, Math.max(24, pts.length * 12), r, 8, false), m, p)
  }
  const extrude = (sh: T.Shape, opts: T.ExtrudeGeometryOptions) => {
    const g = new T.ExtrudeGeometry(sh, opts)
    g.rotateX(-Math.PI / 2)
    return g
  }
  const slab = (p: T.Object3D, r: number, h: number, y: number, m: T.Material) => {
    const sh = new T.Shape()
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 6 + (i * Math.PI * 2) / 6
      const [x, z] = [Math.cos(a) * r, Math.sin(a) * r]
      if (i) sh.lineTo(x, z)
      else sh.moveTo(x, z)
    }
    sh.closePath()
    const g = extrude(sh, { depth: h, bevelEnabled: true, bevelSegments: 3, steps: 1, bevelSize: 0.055, bevelThickness: 0.045, curveSegments: 24 })
    return mesh(g, m, p, 0, y, 0)
  }
  const blob = (p: T.Object3D, r: number, h: number, y: number, m: T.Material, seed = 0, sx = 1, sz = 1) => {
    const sh = new T.Shape()
    for (let i = 0; i <= 64; i++) {
      const a = (i / 64) * Math.PI * 2
      const rr = r * (1 + 0.075 * Math.sin(3 * a + seed) + 0.055 * Math.cos(5 * a + seed))
      const [x, z] = [Math.cos(a) * rr * sx, Math.sin(a) * rr * sz]
      if (i) sh.lineTo(x, z)
      else sh.moveTo(x, z)
    }
    const g = extrude(sh, { depth: h, bevelEnabled: true, bevelSize: 0.022, bevelThickness: 0.023, bevelSegments: 2, curveSegments: 40 })
    return mesh(g, m, p, 0, y, 0)
  }
  const pine = (p: T.Object3D, x: number, z: number, s = 1, y = 0.49) => {
    const g = new T.Group()
    g.position.set(x, y, z)
    p.add(g)
    cylinder(g, 0.035 * s, 0.047 * s, 0.35 * s, C.wood, 0, 0.16 * s, 0, 8)
    for (let i = 0; i < 3; i++) {
      const o = cylinder(g, 0, (0.24 - i * 0.044) * s, (0.4 - i * 0.065) * s, [C.dark, C.pine, C.light][i], 0, (0.36 + i * 0.19) * s, 0, 9)
      o.rotation.y = i * 0.35
    }
  }
  const rockMat = mat('#b4b0a0')
  const rock = (p: T.Object3D, x: number, z: number, s = 1, y = 0.5) => {
    const o = mesh(new T.DodecahedronGeometry(0.13 * s, 0), rockMat, p, x, y + 0.07 * s, z)
    o.scale.set(1.3, 0.65, 0.8)
    o.rotation.set(0.3, x, 0.2)
  }

  // Shadow catcher instead of the source's lit floor: the page's own paper shows through.
  const shadowMat = new T.ShadowMaterial({ opacity: 0.16 })
  mats.push(shadowMat)
  const floor = mesh(new T.PlaneGeometry(60, 60), shadowMat, root, 0, -0.44, 0)
  floor.rotation.x = -Math.PI / 2
  floor.castShadow = false

  const world = new T.Group()
  root.add(world)

  // A quiet circular plinth with fine topographic etchings.
  cylinder(world, 4.65, 4.7, 0.14, C.paper, 0, -0.3, 0, 96)
  cylinder(world, 4.68, 4.68, 0.04, C.edge, 0, -0.395, 0, 96)
  const etch = mat('#cfc6b1')
  for (let k = 0; k < 6; k++) {
    const pts: number[][] = []
    for (let j = 0; j <= 100; j++) {
      const a = (j / 100) * 2 * Math.PI
      const rr = 3.68 + k * 0.14 + 0.05 * Math.sin(5 * a + k * 0.4)
      pts.push([Math.cos(a) * rr, -0.222, Math.sin(a) * rr])
    }
    tube(world, pts, 0.008, etch)
  }

  const tiles: T.Group[] = []
  const tile = (x: number, z: number, top: T.Material, selected = true) => {
    const g = new T.Group()
    g.userData = { x, z, selected }
    g.position.set(x, 0.05, z)
    world.add(g)
    slab(g, 1.47, 0.27, 0.05, C.edge)
    slab(g, 1.44, 0.12, 0.35, C.paper)
    slab(g, 1.39, 0.025, 0.48, top)
    tiles.push(g)
    return g
  }
  const lake = tile(0, 0, mat('#a8b397'))
  const cafe = tile(1.32, 2.28, mat('#cabda0'))
  const forest = tile(1.32, -2.28, mat('#9bac8e'))
  const tea = tile(-1.32, -2.28, mat('#bcc39e'), false)
  const outlook = tile(-1.32, 2.28, mat('#d0c6ad'), false)

  // Lake: contour-cut shoreline, calm water, a wooden jetty.
  blob(lake, 1.07, 0.025, 0.51, mat('#d8cdaf'), 2, 1, 0.73).rotation.y = 0.3
  blob(lake, 0.98, 0.027, 0.548, C.water, 2, 1, 0.73).rotation.y = 0.3
  const ripple = mat('#86b4ae', 0.35)
  for (let k = 0; k < 4; k++) {
    const pts: number[][] = []
    for (let j = 0; j < 24; j++) {
      const a = 0.3 + (j / 23) * 2.7
      pts.push([-0.22 + (0.25 + k * 0.14) * Math.cos(a), 0.583, (0.12 + k * 0.065) * Math.sin(a)])
    }
    tube(lake, pts, 0.008, ripple)
  }
  for (let i = 0; i < 11; i++) box(lake, 0.4, 0.035, 0.075, C.wood, 0.5, 0.615, 0.05 + i * 0.075)
  box(lake, 0.035, 0.075, 0.9, C.gold, 0.28, 0.635, 0.4)
  box(lake, 0.035, 0.075, 0.9, C.gold, 0.72, 0.635, 0.4)
  for (const [x, z, s] of [[-1, 0.3, 0.74], [-0.8, 0.8, 0.8], [0.95, -0.58, 0.8], [0.68, -0.97, 0.7], [-0.5, -0.95, 0.7]]) pine(lake, x, z, s)
  for (let i = 0; i < 5; i++) rock(lake, -1 + i * 0.3, -0.68, 0.8)

  // Café: timber A-frame, terracotta roof, glazed front, a garden terrace.
  const house = new T.Group()
  house.position.set(-0.18, 0.54, -0.1)
  house.rotation.y = -0.24
  cafe.add(house)
  box(house, 1.24, 0.11, 0.96, C.wood, 0, 0.015, 0)
  box(house, 0.87, 0.62, 0.75, mat('#e5d6b8'), 0, 0.36, 0)
  box(house, 0.77, 0.52, 0.014, mat('#6a9c97', 0.23, 0.22), 0, 0.34, 0.39)
  for (const x of [-0.38, -0.13, 0.13, 0.38]) box(house, 0.022, 0.53, 0.034, C.wood, x, 0.34, 0.41)
  box(house, 0.84, 0.022, 0.04, C.wood, 0, 0.3, 0.41)
  const seam = mat('#b95e38')
  for (const sign of [-1, 1]) {
    box(house, 0.77, 0.055, 1.02, C.terra, sign * 0.282, 0.805, 0).rotation.z = sign * 0.66
    for (let j = 0; j < 9; j++) box(house, 0.775, 0.009, 0.012, seam, sign * 0.284, 0.844, -0.45 + j * 0.112).rotation.z = sign * 0.66
  }
  box(house, 0.13, 0.5, 0.14, C.wood, 0.24, 0.9, -0.27)
  box(cafe, 1.68, 0.07, 0.67, C.wood, 0.2, 0.545, 0.7)
  for (let j = 0; j < 12; j++) box(cafe, 0.015, 0.01, 0.66, C.edge, -0.55 + j * 0.137, 0.588, 0.7)
  for (const x of [-0.36, 0.62]) {
    cylinder(cafe, 0.2, 0.2, 0.034, C.white, x, 0.8, 0.77)
    cylinder(cafe, 0.023, 0.023, 0.23, C.gold, x, 0.665, 0.77)
    for (const dx of [-0.26, 0.26]) {
      box(cafe, 0.16, 0.03, 0.15, C.dark, x + dx, 0.675, 0.8)
      for (const dz of [-0.055, 0.055]) box(cafe, 0.015, 0.17, 0.015, C.wood, x + dx, 0.58, 0.8 + dz)
    }
  }
  cylinder(cafe, 0, 0.51, 0.17, C.white, 0.73, 1.45, 0.65, 16)
  cylinder(cafe, 0.015, 0.015, 0.77, C.gold, 0.73, 1.04, 0.65)
  pine(cafe, -1, -0.61, 0.88)
  pine(cafe, 0.84, -0.6, 0.8)
  for (const x of [-0.9, 1.06]) {
    cylinder(cafe, 0.12, 0.1, 0.2, C.terra, x, 0.61, 0.56)
    mesh(new T.IcosahedronGeometry(0.16, 1), C.light, cafe, x, 0.82, 0.56)
  }

  // Pine ridge: stacked contours, a lookout trail, a small bench.
  const ridge = ['#91a480', '#859b73', '#779168', '#6e885e', '#637e53']
  for (let i = 0; i < 5; i++) {
    const hill = blob(forest, 1.03 - i * 0.12, 0.07, 0.52 + i * 0.075, mat(ridge[i]), 1, 1, 0.88)
    hill.position.x = -0.12
    hill.position.z = -0.2
  }
  const trail: number[][] = []
  for (let i = 0; i < 50; i++) {
    const a = i / 49
    trail.push([-0.7 + 1.25 * a, 0.89, 0.75 - 0.65 * a + 0.13 * Math.sin(a * 2 * Math.PI)])
  }
  tube(forest, trail, 0.027, C.paper)
  for (const [x, z, s, y] of [[-0.7, -0.3, 0.95, 0.85], [0.12, -0.5, 0.85, 0.91], [0.66, -0.45, 1, 0.77], [-0.75, 0.25, 0.75, 0.73], [0.52, 0.38, 0.73, 0.68], [0.95, 0.09, 0.7, 0.56]]) pine(forest, x, z, s, y)
  box(forest, 0.4, 0.035, 0.16, C.wood, 0.28, 0.99, 0.15)
  for (const x of [0.14, 0.42]) box(forest, 0.025, 0.15, 0.025, C.gold, x, 0.9, 0.15)

  // Tea contours (an alternative, left unchosen).
  const teaShades = ['#a4b184', '#94a572', '#849960', '#768d55']
  for (let i = 0; i < 4; i++) blob(tea, 0.97 - i * 0.16, 0.055, 0.52 + i * 0.06, mat(teaShades[i]), 4, 1, 0.88).position.set(0, 0.52 + i * 0.06, -0.05)
  for (let k = 0; k < 8; k++) {
    const pts: number[][] = []
    for (let j = 0; j < 30; j++) {
      const x = -0.86 + (j / 29) * 1.72
      const z = -0.75 + k * 0.2 + 0.065 * Math.cos(x * 3)
      if (x * x + z * z < 1.14) pts.push([x, 0.77 + 0.015 * Math.cos(x * 3), z])
    }
    if (pts.length > 2) tube(tea, pts, 0.035, C.dark)
  }
  pine(tea, -0.98, 0.1, 0.6)
  pine(tea, 0.88, -0.4, 0.6)

  // Outlook (the other alternative): a cream tent on a terraced knoll.
  const knoll = ['#b8b896', '#a9ad88', '#9b9f7b']
  for (let i = 0; i < 3; i++) blob(outlook, 1.06 - i * 0.24, 0.065, 0.52 + i * 0.075, mat(knoll[i]), 6, 1, 0.76)
  const tent = mesh(new T.ConeGeometry(0.53, 0.6, 4), C.white, outlook, -0.12, 1.03, -0.2)
  tent.rotation.y = Math.PI / 4
  tent.scale.z = 1.3
  box(outlook, 0.22, 0.25, 0.012, C.wood, -0.12, 0.87, 0.31)
  pine(outlook, -0.84, -0.35, 0.76, 0.61)
  pine(outlook, 0.82, -0.3, 0.75, 0.62)

  // Enamel markers on the chosen three.
  const pins: T.Group[] = []
  const pin = (parent: T.Object3D, x: number, z: number, y: number) => {
    const g = new T.Group()
    g.position.set(x, y, z)
    parent.add(g)
    cylinder(g, 0.017, 0.027, 0.24, C.gold, 0, 0.12, 0)
    mesh(new T.TorusGeometry(0.15, 0.052, 12, 40), C.orange, g, 0, 0.38, 0).rotation.y = 0.51
    mesh(new T.SphereGeometry(0.04, 16, 12), C.white, g, 0, 0.38, 0)
    pins.push(g)
  }
  pin(cafe, 0.63, -0.52, 1.05)
  pin(lake, -0.63, 0.25, 0.77)
  pin(forest, 0.6, 0.25, 1.12)

  // The thread between the chosen three, revealed by draw range.
  const curve = new T.CatmullRomCurve3(
    [[1.95, 0.72, 2.1], [1.35, 0.68, 1.22], [0.55, 0.7, 0.92], [-0.48, 0.66, 0.54], [-0.86, 0.7, -0.05], [-0.35, 0.69, -1], [0.71, 0.74, -1.5], [1.91, 1.02, -2.04]].map(
      ([x, y, z]) => new T.Vector3(x, y, z),
    ),
  )
  const routeG = new T.TubeGeometry(curve, 180, 0.027, 8, false)
  const route = mesh(routeG, C.orange, world)
  const bead = mesh(new T.SphereGeometry(0.073, 20, 16), C.orange, world)
  const routeCount = routeG.index!.count

  // A knurled compass for a tactile travel accessory.
  const compass = new T.Group()
  compass.position.set(3.25, 0.12, 2.05)
  world.add(compass)
  cylinder(compass, 0.43, 0.43, 0.1, C.gold, 0, 0, 0, 64)
  cylinder(compass, 0.375, 0.375, 0.035, C.white, 0, 0.071, 0, 64)
  for (let k = 0; k < 32; k++) {
    const a = (k / 32) * Math.PI * 2
    box(compass, 0.015, 0.01, k % 4 === 0 ? 0.065 : 0.033, C.wood, Math.sin(a) * 0.325, 0.099, Math.cos(a) * 0.325).rotation.y = a
  }
  const needle = new T.Group()
  needle.position.y = 0.12
  compass.add(needle)
  mesh(new T.ConeGeometry(0.062, 0.26, 3), C.terra, needle, 0, 0, -0.11).rotation.x = Math.PI / 2
  mesh(new T.ConeGeometry(0.062, 0.26, 3), C.dark, needle, 0, 0, 0.11).rotation.x = -Math.PI / 2
  mesh(new T.SphereGeometry(0.027, 16, 12), C.gold, compass, 0, 0.138, 0)

  const update = (choose: number, time: number) => {
    const a = (time / 14) * Math.PI * 2
    const settle = smooth((choose - 1 / 3) * 3)
    const reveal = smooth((choose - 2 / 3) * 3)
    const spread = 1 - settle
    world.rotation.y = 0.035 * Math.sin(a)
    world.position.y = 0.035 * Math.sin(a)
    tiles.forEach((g, i) => {
      const { x, z, selected } = g.userData as { x: number; z: number; selected: boolean }
      const f = selected ? 1 + 0.25 * spread : 1 + 0.5 * settle
      // Unchosen tiles sink and shrink a little as they drift: set aside, not deleted.
      const y = selected ? 0.04 + 0.15 * spread : 0.17 - 0.2 * settle
      g.position.set(x * f, y + 0.035 * Math.sin(a + i * 0.7), z * f)
      g.rotation.y = (selected ? 0.045 : -0.045) * Math.sin(a + i * 0.8)
      if (!selected) g.scale.setScalar(1 - 0.18 * settle)
    })
    route.visible = reveal > 0.001
    routeG.setDrawRange(0, Math.floor((routeCount * reveal) / 48) * 48)
    bead.visible = reveal > 0.01 && reveal < 0.99
    if (bead.visible) bead.position.copy(curve.getPointAt(reveal))
    pins.forEach((p, i) => p.scale.setScalar(0.82 + 0.18 * settle + 0.035 * Math.sin(a + i)))
    // The needle settles on the route once there is one.
    needle.rotation.y = 0.9 * (1 - reveal) * Math.sin(a * 2) + reveal * -0.6
  }
  update(0, 0)

  return {
    group: root,
    update,
    dispose: () => {
      geos.forEach((g) => g.dispose())
      mats.forEach((m) => m.dispose())
    },
  }
}

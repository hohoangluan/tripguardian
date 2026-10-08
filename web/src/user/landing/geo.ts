// Map geometry shared by the 3D scene and the landscape baker (web/scripts/landscape): real coordinates onto the
// scene's units. Pure constants and functions; no data, no three.js.

export const BOUNDS = { s: 11.86, n: 12.03, w: 108.38, e: 108.6 }
export const UNIT_KM = 0.2 // one scene unit = 200 m on the ground
const KM_LAT = 110.6
const KM_LNG = 108.9 // at ~12°N
export const W = ((BOUNDS.e - BOUNDS.w) * KM_LNG) / UNIT_KM
export const D = ((BOUNDS.n - BOUNDS.s) * KM_LAT) / UNIT_KM

// The elevation grid the ground is drawn from (web/scripts/export_landscape.py); bigger than BOUNDS so the camera
// never sees an edge from the valley.
export const DEM = { lat0: 11.695, lat1: 12.195, lng0: 108.19, lng1: 108.79 }
export const WORLD = { w: ((DEM.lng1 - DEM.lng0) * KM_LNG) / UNIT_KM, d: ((DEM.lat1 - DEM.lat0) * KM_LAT) / UNIT_KM }
export const GRID = { nx: 380, nz: 322 } // ground mesh segments over WORLD
export const EXAG = 3.2 // scene units of height per 200 m of real height
export const BASE_M = 1480 // the town's own elevation
export const TOWN_Y = 3.4

export const inBounds = (lat: number, lng: number) => lat > BOUNDS.s && lat < BOUNDS.n && lng > BOUNDS.w && lng < BOUNDS.e
// north is -z, east is +x
export const toXZ = (lat: number, lng: number): [number, number] => [
  ((lng - BOUNDS.w) * KM_LNG) / UNIT_KM - W / 2,
  ((BOUNDS.n - lat) * KM_LAT) / UNIT_KM - D / 2,
]
export const toLatLng = (x: number, z: number): [number, number] => [BOUNDS.n - ((z + D / 2) * UNIT_KM) / KM_LAT, BOUNDS.w + ((x + W / 2) * UNIT_KM) / KM_LNG]

// real places the scene names or builds on
export const LANDMARKS = {
  langbiang: toXZ(12.0453, 108.441), // the twin peaks Bà and Ông
  cathedral: toXZ(11.9358, 108.4439), // Nhà thờ Chánh Tòa, "Nhà thờ Con Gà"
  centre: toXZ(11.9445, 108.4462), // around Hồ Xuân Hương
}

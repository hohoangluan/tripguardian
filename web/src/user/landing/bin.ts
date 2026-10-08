// The baked landscape file, fetched once. index.html starts the request while the scripts are still loading
// (window.__tgLand); the landing reuses that promise, so the download never waits for the 3D chunk.
const URL_ = '/world/dalat.bin'
declare global { interface Window { __tgLand?: Promise<ArrayBuffer> } }

export function fetchLandscape(): Promise<ArrayBuffer> {
  return (window.__tgLand ??= fetch(URL_).then((r) => {
    if (!r.ok) throw new Error(`landscape ${r.status}`)
    return r.arrayBuffer()
  }))
}

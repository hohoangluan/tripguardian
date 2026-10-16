// Reads public/data/snapshot.json off the main thread. The file is tens of MB: parsing it where the screens run
// freezes the page when the visitor moves on to Lựa chọn. The places come back in small batches, so the page
// only ever does a little work at a time (data/store.ts assembles them).

const BATCH = 150

self.onmessage = async (event) => {
  try {
    const res = await fetch(event.data?.url ?? '/data/snapshot.json')
    if (!res.ok) throw new Error(`snapshot ${res.status}`)
    const { places, ...head } = (await res.json()) as { places: unknown[] } & Record<string, unknown>
    self.postMessage({ head, total: places.length })
    for (let i = 0; i < places.length; i += BATCH) self.postMessage({ places: places.slice(i, i + BATCH) })
    self.postMessage({ done: true })
  } catch (e) {
    self.postMessage({ error: String(e) })
  }
}

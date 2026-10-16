import { useEffect, useState } from 'react'
import { readRoutes } from '../../planning/api'
import type { DayRoute } from '../../planning/types'

// The drawn path of each day, read apart from the plan so an edit never waits for the routing source.
// `key` changes whenever the itinerary does (order, days, lodging); until the new paths arrive the map keeps the
// old line only if it still belongs to the same itinerary, otherwise it falls back to the dashed sketch.
export function useRoutes(planningId: string | null, key: string, on: boolean) {
  const [got, setGot] = useState<{ key: string; days: DayRoute[] } | null>(null)
  useEffect(() => {
    if (!planningId || !on) return
    let live = true
    readRoutes(planningId).then((r) => { if (live) setGot({ key, days: r.days }) }).catch(() => { if (live) setGot({ key, days: [] }) })
    return () => { live = false }
  }, [planningId, key, on])
  return got && got.key === key ? got.days : null
}

// Shape of public/data/snapshot.json (written by scripts/export_snapshot.py).

export type Status = 'VERIFIED' | 'UNCERTAIN' | 'OUTDATED' | 'NEEDS_REVIEW' | 'DISABLED'
export type Group = 'sight' | 'food' | 'shop' | 'other'
export type Trend = 'rising' | 'falling' | 'stable' | 'insufficient'
export type DayKey = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'
export type CrowdTable = Partial<Record<'weekday' | 'weekend', Record<string, number>>> & {
  peak?: { day: DayKey; hour: number; pct: number } | null
}

export interface Quote {
  text: string
  date: string | null
  source: string
}

export interface Signal {
  id: string
  value: string
  distribution: Record<string, number>
  n: number
  agreement: number
  freshnessDays: number | null
  sourceTypes: string[]
  bySource: Record<string, number>
  byContext: Record<string, Record<string, number>>
  mentionRate: number | null
  trend: Trend
  authority: string | null
  status: Status
  rawStatus: string
  quotes: Quote[]
}

export interface Video {
  id: string
  url: string
  handle: string | null
  desc: string
  local?: boolean // the clip is on our server (/media/tiktok/<id>/video.mp4); else TikTok's embedded player
}

export interface PriceRange {
  min_vnd: number
  max_vnd: number
  per: string
  reports: number
}

// What earlier visitors said about a place, as served (src/corpus/serving/details.py) and cut by export_snapshot.py.
export interface DetailQuote {
  text: string
  date: string | null
  source: string
}

export interface DetailItem {
  text: string
  n: number // independent people who said it
  status: Status
  reason: string | null
  quotes?: DetailQuote[]
  amount_vnd?: number
  audience?: string
  unit?: string
  min_people?: number
  months?: number[]
  days?: string[]
  hour?: string
}

export interface TimeWindow {
  by_time_of_day: Record<string, number>
  hours: string[]
  items: DetailItem[]
}

export interface Fit {
  value: 'good' | 'bad' | 'conditional'
  distribution: Record<string, number>
  n: number
  reasons: string[]
  status: Status
  quotes?: DetailQuote[]
}

export interface PlaceDetails {
  known_for?: { headline: DetailItem | null; more: DetailItem[] }
  order?: DetailItem[]
  avoid?: DetailItem[]
  activity?: DetailItem[]
  photo_spot?: DetailItem[]
  access?: DetailItem[]
  booking?: DetailItem[]
  bring?: DetailItem[]
  situation?: DetailItem[]
  cost?: {
    entry: Partial<Record<'adult' | 'child' | 'senior', { vnd: number; source: 'official' | 'reviews' } | null>>
    parking: DetailItem | null
    extras: DetailItem[]
    per_party: DetailItem[]
    total_vnd: { base: number; with_extras: number } | null
    kind: 'fact' | 'estimate'
  } | null
  timing?: {
    best_time: TimeWindow
    avoid_time: TimeWindow
    best_months: number[]
    avoid_months: number[]
    schedule: DetailItem[]
    last_entry: { time: string; source: 'official' | 'reviews' } | null
  }
  fit?: Record<string, Fit>
  relations?: { quieter: string[]; busier: string[] }
  walk_to_night_market_min?: number | null
}

export interface Place {
  id: string
  name: string
  category: string | null
  group: Group
  lat: number
  lng: number
  address: string | null
  mapsUrl: string | null
  rating: number | null
  reviewCount: number | null
  hoursText: string[]
  googleStatus: string | null
  attributes: string[]
  kind: 'experience' | 'inventory'
  asOf?: string
  voices?: number
  coverage?: Record<string, 'COMPLETE' | 'PARTIAL' | 'NONE'>
  hours?: Partial<Record<DayKey, [string, string][]>> | null
  closure?: unknown
  priceRange?: PriceRange | null
  crowdByTime?: CrowdTable | null
  ratingTrend?: { recent_mean: number | null; older_mean: number | null; direction: Trend; recent_n: number; older_n: number } | null
  features: Signal[]
  details?: PlaceDetails
  proposed?: { label: string; count: number; authors: number }[]
  videos: Video[]
}

export interface ReviewItem {
  id: string
  kind: 'judge_flag' | 'permissive_check' | 'conflict' | 'proposed_feature'
  placeId: string
  feature: string
  value: string
  sample: boolean
}

export interface Snapshot {
  asOf: string
  city: string
  places: Place[]
  review: ReviewItem[]
  decisions: { at: string; kind: string; id: string; decision: string; note?: string }[]
  build: { at: string; places: number; stale_files: number; coverage: Record<string, number> }
  system: {
    observe: { at: string; places: number; status: Record<string, number>; observations: Record<string, number> } | null
    errors: { at: string | null; source: string; stage: string | null; ref: string | null; error: string }[]
    videos: number
    gmapsPlaces: number
  }
}

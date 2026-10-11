# Algorithmic Architecture: Supporting Modules

## Overview

TripGuardian consists of several core system modules working in parallel to support the main trip planning pipeline (Trip Understanding, Decision, Planning). This document outlines the technical architecture of these supporting systems for competition judges.

---

## 1. **Live Context Module** (`src/live/`)

### Purpose
Fetches real-time, external data per request to enrich planning decisions with current facts. Never modifies persistent Place Intelligence—only maintains temporary cache under `data/live/`.

### Key Principles
- **No Hallucination Rule**: Every value carries `source` and `fetched_at` metadata; missing data raises `Unavailable` rather than inventing values
- **Estimate Marking**: All returned data labeled as estimates, enabling downstream modules to make qualified decisions
- **Read-Only**: Never writes to Place Intelligence database; cache is ephemeral

### Sub-Components

| Component | Function | Algorithm |
|-----------|----------|-----------|
| **Flights** | Real-time flight search & availability | Call flight API aggregators; parse price, duration, departure times |
| **Buses** | Public transit schedule lookup | Query transit provider APIs; compute arrival/departure windows |
| **Lodging** | Accommodation availability & pricing | Search lodging APIs (e.g., Booking.com, Airbnb); filter by date/budget |
| **Weather** | Forecasts for trip location | Fetch 7-14 day forecasts; mark uncertainty based on distance from prediction date |
| **Geocoding** | Location coordinate resolution | Convert addresses ↔ lat/lon; handle ambiguity with confidence scores |
| **Routes (OSRM)** | Travel time & distance matrices | Call Open Source Routing Machine; compute travel_matrix for stop-to-stop times |
| **Holidays** | Public holiday calendars | Query holiday API per destination; flag for availability/pricing effects |
| **Sun Times** | Sunrise/sunset calculations | Compute from lat/lon + date; enable time-sensitive activity matching |
| **Advisories** | Travel warnings & safety info | Aggregate from official sources; provide confidence levels |

### Data Flow
```
User Request → Live Module → External APIs → Cache (data/live/)
                                   ↓
                         Attach: source, fetched_at
                                   ↓
                            Return to Planning
```

---

## 2. **Companion Module** (`src/companion/`)

### Purpose
Manages the **"Đang đi"** (Currently Going) live trip state: check-ins, skip/rate actions, and real-time suggestions for the user *during* trip execution.

### Core Algorithm: Day-by-Day Trip State Machine

```
Trip Phases:
  - planned      → active (first check-in) → done (end_date passed)
  - Each Stop: planned → arrived (check-in) | skipped
```

### Key Operations

#### 1. **Trip Synchronization** (`sync()`)
- Reads confirmed Planning itinerary
- Creates/updates `trips` and `trip_stops` rows in DB
- Tracks plan state: dates, stop sequence, expected arrival/departure times

#### 2. **Daily View Compilation** (`today()`)
- Filters stops by current day (relative to trip start)
- Shows stop status: planned, arrived, skipped, off-plan
- Computes "tight" schedule detection: if user arrived >N minutes late and unvisited stops remain

#### 3. **Suggestion Engine** (`suggestions()`)
Uses modular scoring for nearby place recommendations:
- **Play** (`suggest.play`): ranked by user's stated interests
- **Practical** (`suggest.practical`): filters by amenities (parking, hours, etc.)
- **Timely** (`suggest.timely`): accounts for daylight availability (sun_times)
- **Nearby** (`suggest.nearby`): spatial + temporal proximity with budget constraints

```
Budget Calculation:
  - budget_min = minutes until next planned stop (if today)
  - else: minutes until day_end (configurable, e.g., 22:00)
```

#### 4. **Quality Assurance** (`quality()`)
- Validates hard_filters (corpus hard_check results) against planned places
- Reports: fail count (must be 0), unknown check share

### Check-in Logic
```
If stop_id given:
  - Must be on its own day
  - Updates stop status → 'arrived'
  - Activates trip if still 'planned'
  
Else if place_id given:
  - Must be a known served place
  - Only during active trip dates
  - Creates off-plan check-in row (stop_id = NULL)
```

### Stored Trip State
- `trips`: journey_id, start_date, end_date, status, updated_at
- `trip_stops`: place_id, day, seq, status, planned_arrive, planned_leave, arrived_at, rating, skip_reason
- `checkins`: trip_id, stop_id (nullable), place_id, at (timestamp)
- `calendar_sync`: Google Calendar sync state (for export confirmation)

---

## 3. **Analytics Module** (`src/analytics/`)

### Purpose
Provides read-only, real-time metrics for Admin dashboard and journey replay/debugging via Postgres queries with read-only role.

### Funnel Analysis

**7-Stage Journey Funnel** (product flow sequence):
1. **Tạo hành trình** (Create journey)
2. **Trip hiểu xong** (Trip understanding compiled)
3. **Thấy shortlist** (Decision shortlist shown)
4. **Chọn ≥ 1 nơi** (User selects ≥1 place)
5. **Lịch xem trước sẵn sàng** (Preview calendar ready)
6. **Vào Lịch trình** (User enters planning stage)
7. **Chốt lịch** (Confirmed itinerary)
8. **Gửi phản hồi** (Feedback submitted)

#### Funnel Query Algorithm
```
Input: Date range [from, to] (UTC+7, whole days)
       Optional filters: start_with, app_version

1. Query journeys created in [from, to]
   - Match filters (start_with, app_version)
   - Result: journey_id → creation_time

2. For each stage:
   a. Count journeys reaching this stage
   b. Compute retention % from previous stage
   c. Measure median time-to-stage (excluding imported journeys)
   d. If journey stopped at this stage:
      - Record last event name
      - Surface top 3 abandonment reasons

Output: [
  {
    key: "created",
    label: "...",
    journeys: N,
    kept: %,
    median_min: X.X,
    stopped: Y,
    last_before_stop: [(event, count), ...]
  },
  ...
]
```

### Query Types

| Query | Metric | Algorithm |
|-------|--------|-----------|
| **funnel()** | Stage adoption, retention, time-to-stage | Event filtering by name/props; time diffs; percentiles |
| **decision()** | Decision actions, drop reasons, preview status | Group events by action type; rank by frequency |
| **sessions()** | Journey listing + filters | SELECT from journeys table; apply state filters (error, feedback score, etc.) |
| **session()** | Single journey replay | Fetch envelope (snapshots, receipts), events timeline, feedback history |
| **today()** | Dashboard "Hôm nay" metrics | Count events in last 24h; new users/guests signup |
| **versions()** | Active app versions | Group by version; rank by recency of event |

### Error & Quality Tracking
- **Error Rate**: Events with `props.error` or `props.path = 'fallback'`
- **Feedback Quality**: Minimum score per journey; filters for low_feedback (≤2/5)
- **Search Misses**: Queries returning 0 results; ranked by frequency

### Data Integrity
- Uses read-only database connection pool (no writes)
- Handles `imported` journeys (time source unreliable) separately
- Normalizes timezones to Asia/Ho_Chi_Minh (UTC+7)

---

## 4. **Database Layer** (`src/db/`)

### Purpose
Centralized Postgres connection pooling and schema migration management.

### Architecture

#### Connection Pool (`pool.py`)
- Single shared pool per database URL
- Thread-safe, reusable connections
- Reduces overhead of repeated connect/disconnect

#### Migration System (`migrate.py`)
- Numbered SQL files in `migrations/` directory
- Sequential execution guarantees idempotence
- Tracks migration state in `schema_migrations` table

```
Migration Pattern:
  migrations/001_init_users.sql
  migrations/002_add_journeys.sql
  migrations/003_add_events.sql
  ...
```

**Bootstrap Flow**:
1. Check if DB exists; create if not
2. Ensure `schema_migrations` table
3. Find highest applied migration
4. Apply pending migrations in order

### Public API
- `pool()` → connection pool instance
- `database_url()` → parsed connection URL
- `migrate(pool)` → run pending migrations
- `bootstrap(db_url)` → initialize DB + apply migrations
- `MIGRATIONS` → list of migration files

---

## 5. **Accounts Module** (`src/accounts/`)

### Purpose
Manages user authentication (Google Sign-In), sessions, profiles, avatars, and Calendar integration.

### Authentication Flow

```
1. User clicks "Sign in with Google"
2. GoogleClient exchanges auth_code for ID + access tokens
3. Extract: email, display_name, picture (avatar)
4. Lookup/create user in DB
5. Create session + auth cookie
6. Return: user object, session token
```

### Key Components

| Component | Function |
|-----------|----------|
| **GoogleClient** | OAuth 2.0 token exchange, ID token verification |
| **Session Management** | Create, validate, revoke sessions |
| **Profile API** | Get/update display_name, avatar |
| **Avatar Storage** | Upload/retrieve with size validation (AVATAR_MAX_BYTES) |
| **Calendar Scope** | OAuth scope for Google Calendar read access (`CALENDAR_SCOPE`) |
| **Deletion** | Soft-delete user + cascade to journeys, events |

### Security
- **Terms Version**: tracks TOS acceptance; re-prompts on update
- **safe_next**: validates redirect URLs to prevent open redirect
- **AuthError**: handles invalid tokens, expired sessions, permission issues

### Database Schema
- `users`: id, email, display_name, avatar_blob, role, created_at, deleted_at
- `sessions`: user_id, token, expires_at, created_at

---

## 6. **Corpus Module** (`src/corpus/`)

### Purpose
Large-scale data collection, curation, and knowledge base building for Place Intelligence. Modular pipeline: crawl → judge → aggregate → serving.

### Data Ingestion Pipeline

#### Sources & Phases
Three parallel data streams converge:

| Source | Phases | Purpose |
|--------|--------|---------|
| **TikTok** | search → list → filter → crawl (14 phases total) | Extract venue info, user reviews, video evidence from TikTok |
| **Google Maps** | search → filter → counts → crawl → observe (9+ phases) | Authoritative business info, photos, reviews, ratings |
| **Official** | pages → observe | Hotel/restaurant official websites, verified pricing |
| **Reports** | observe | Crowdsourced traveler reviews/reports |

#### Key Phases

**Crawl Phase** (browser automation):
- Parallel-capable (multiple processes/shards for TikTok)
- Fetches raw HTML/video data from sources
- Stores in todo/done file structure

**ASR Phase** (TikTok video processing):
- Automatic speech recognition on videos
- Transcribes verbal mentions of places/activities
- Can shard across multiple GPUs

**Judge Phase** (LLM-based labeling):
- **Dedup**: Identifies duplicate place claims across sources
- **Status**: Labels venue status (open/closed/seasonal)
- **Audit**: LLM verification of structured claims with fallback to human review

**Aggregate Phase**:
- Merges observations from all sources
- Builds Place Intelligence: facts + evidence links
- Produces: `data/intel/places/`

**Serving Phase**:
- Optimizes intel for real-time queries
- Indexes by category, distance, amenity
- Exports: `data/serving/places.json` (for Place Decision consumption)

### Concurrency Model
```
SHARDABLE = {place_search, place_crawl, comments_crawl}  # TikTok multi-account
Browser phases: one core per process (crawl saturates ~8 tabs)
ASR/asr_check: one GPU each (parallel GPU-enabled servers)
place_verify: one process per Gemma endpoint
```

### Build Orchestration
```bash
python -m corpus build --city dalat --every 30  # Repeat every 30 min
  → qc (Google Maps quality check)
  → observe (all sources)
  → judge (dedup, status, audit)
  → aggregate
  → serving
  → (hot-reload Place Decision with new intel)
```

### Data Model
```
Place Intelligence Row:
  {
    id: place_id,
    identity: {name, category, address, ...},
    context: {neighborhood, opening_hours, ...},
    evidence: {
      "facts": [
        {"claim": "...", "source": "tiktok|gmaps|official", "confidence": 0.95, "vid_ids": [...]}
      ]
    }
  }
```

---

## System Integration Map

```
┌─────────────────────────────────────────────────────────────┐
│                    User Journey                             │
├─────────────────────────────────────────────────────────────┤
│
│  Trip Understanding
│         ↓
│  Decision (Place Selection)
│    ↑     ↓
│    └─────→ Planning (Itinerary Sequencing)
│              ↓
│         Companion (Live Execution)
│           ↗     ↘
│      Check-in   Suggestions
│       (status)   (nearby places + timely)
│           ↓
│         Analytics (Funnel & Replay)
│
├─────────────────────────────────────────────────────────────┤
│  Supporting Infrastructure                                  │
├─────────────────────────────────────────────────────────────┤
│
│  Live Context (Per-Request Enrichment)
│    ├─ Flights, Buses, Lodging (Availability)
│    ├─ Weather, Sun, Advisories (Conditions)
│    ├─ Geocoding, OSRM (Spatial)
│    └─ Holidays, Events (Calendar)
│
│  Accounts (User Management)
│    ├─ Google OAuth
│    ├─ Sessions
│    └─ Calendar Export
│
│  Database (Postgres Pool + Migrations)
│
│  Corpus (Place Intelligence)
│    ├─ Multi-source crawl (TikTok, Maps, Official)
│    ├─ Judge (LLM + human review)
│    ├─ Aggregate → Serving
│    └─ Hot-reload Decision
│
└─────────────────────────────────────────────────────────────┘
```

---

## Performance & Scalability Considerations

### Companion Module
- **Check-in write**: INSERT into `checkins` table (< 100ms)
- **Daily view**: 1-2 table joins, index on journey_id (< 50ms)
- **Suggestions**: O(N) nearest-neighbor search (N = # served places)

### Analytics Module
- **Funnel**: Single table scan + grouping; suitable for dashboards (< 2s)
- **Session replay**: Pre-fetched envelope JSON; O(1) by journey_id
- **Funnels filter by date range**: Improves query selectivity

### Live Module
- **Per-request**: External API calls cached under `data/live/`; TTL configurable per source
- **Unavailable handling**: Graceful degradation; never blocks pipeline

### Corpus Module
- **Crawl**: Parallelizable by city + source via sharding
- **Judge**: LLM batch processing; fallback to human queue if uncertain
- **Serving**: Delta updates; only changed places re-indexed

---

## Testing & Observability

### Analytics & Replay
- All journeys' events captured in `events` table
- Envelope snapshots preserve module logs (trip/decision/planning)
- Replay: reconstruct journey state from events + envelope

### Corpus Quality
- Review server (`corpus review`) for manual judgment QA
- Dedup audits track false-positive merges
- Observability: phase-by-phase progress logging

### Accounts
- Session token rotation on activity
- Soft-delete maintains audit trail
- Avatar upload validation (size, format)

---

## Conclusion

TripGuardian's supporting modules form a cohesive system:
- **Live Context** provides real-time facts with honest uncertainty
- **Companion** manages live trip execution with state machine discipline
- **Analytics** enables product insights and debugging
- **Accounts** handles secure user identity
- **Database** ensures transactional reliability
- **Corpus** builds and maintains the Place Intelligence asset

Together, they enable the core planning pipeline to make high-quality, evidence-grounded recommendations.

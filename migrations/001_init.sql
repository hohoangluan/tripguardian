-- Accounts, journeys, events, trips, calendar, notifications (docs/ACCOUNTS.md, docs/ANALYTICS.md, docs/P5_COMPANION.md).
-- Unqualified names: the runner applies this in the connection's current schema (tests use a throwaway schema).

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext UNIQUE,
    google_sub text UNIQUE,
    display_name text,
    picture_url text,
    avatar_key text,
    role text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
    last_login_at timestamptz,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    token_hash bytea PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    user_agent text,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auth_sessions_user ON auth_sessions (user_id);

CREATE TABLE oauth_states (
    state text PRIMARY KEY,
    purpose text NOT NULL CHECK (purpose IN ('login', 'calendar')),
    next text NOT NULL,
    verifier text NOT NULL,
    user_id uuid REFERENCES users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE profiles (
    user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    home_city text,
    usual_mobility text,
    usual_companions text,
    consents jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE calendar_links (
    user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    refresh_token_enc bytea,
    scopes text[] NOT NULL DEFAULT '{}',
    connected_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE journeys (
    id text PRIMARY KEY,
    user_id uuid REFERENCES users (id) ON DELETE SET NULL,
    stage text NOT NULL,
    revision integer NOT NULL,
    envelope jsonb NOT NULL,
    app_version text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX journeys_user ON journeys (user_id, updated_at DESC);

CREATE TABLE feedback (
    id bigserial PRIMARY KEY,
    journey_id text NOT NULL,
    user_id uuid REFERENCES users (id) ON DELETE SET NULL,
    at timestamptz NOT NULL DEFAULT now(),
    scores jsonb NOT NULL DEFAULT '{}',
    more_search boolean,
    note text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feedback_journey ON feedback (journey_id);

CREATE TABLE events (
    id bigserial PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT now(),
    user_id uuid REFERENCES users (id) ON DELETE SET NULL,
    journey_id text,
    source text NOT NULL CHECK (source IN ('server', 'client')),
    name text NOT NULL,
    props jsonb NOT NULL DEFAULT '{}',
    app_version text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_name_at ON events (name, at);
CREATE INDEX events_journey ON events (journey_id);

CREATE TABLE trips (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    journey_id text NOT NULL UNIQUE,
    user_id uuid REFERENCES users (id) ON DELETE SET NULL,
    start_date date,
    end_date date,
    status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'active', 'done')),
    plan_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX trips_user ON trips (user_id);

CREATE TABLE trip_stops (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    day integer NOT NULL,
    seq integer NOT NULL,
    place_id text NOT NULL,
    name text NOT NULL DEFAULT '',
    planned_arrive timestamptz,
    planned_leave timestamptz,
    status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'arrived', 'skipped')),
    arrived_at timestamptz,
    skip_reason text,
    rating smallint CHECK (rating IN (-1, 1)),
    added_on_trip boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX trip_stops_trip ON trip_stops (trip_id, day, seq);

CREATE TABLE checkins (
    id bigserial PRIMARY KEY,
    trip_id uuid NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    stop_id uuid REFERENCES trip_stops (id) ON DELETE SET NULL,
    place_id text NOT NULL,
    at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX checkins_trip ON checkins (trip_id, at);

-- No foreign key to trip_stops: a stop dropped by a new plan keeps its row here until Calendar deletes its event.
CREATE TABLE calendar_events (
    stop_id uuid PRIMARY KEY,
    trip_id uuid NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    google_event_id text NOT NULL,
    etag text,
    synced_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE calendar_sync (
    trip_id uuid PRIMARY KEY REFERENCES trips (id) ON DELETE CASCADE,
    state text NOT NULL DEFAULT 'none' CHECK (state IN ('none', 'synced', 'drifted')),
    calendar_id text,
    synced_plan_hash text,
    last_preview jsonb,
    preview_hash text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE push_subscriptions (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    endpoint text NOT NULL UNIQUE,
    p256dh text NOT NULL,
    auth text NOT NULL,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notification_prefs (
    user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    enabled_kinds text[],
    quiet_start time NOT NULL DEFAULT '22:00',
    quiet_end time NOT NULL DEFAULT '07:00',
    paused_until timestamptz,
    ignored_streak integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users (id) ON DELETE SET NULL,
    trip_id uuid REFERENCES trips (id) ON DELETE SET NULL,
    kind text NOT NULL,
    template_id text,
    variant text,
    payload jsonb NOT NULL DEFAULT '{}',
    scheduled_at timestamptz NOT NULL,
    sent_at timestamptz,
    opened_at timestamptz,
    action text,
    status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'sent', 'skipped', 'cancelled')),
    skip_reason text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_due ON notifications (status, scheduled_at);
CREATE INDEX notifications_user ON notifications (user_id, created_at DESC);

-- Analytics reads everything except secrets (session hashes, OAuth state, Google tokens, push keys).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tg_analytics') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO tg_analytics', current_schema());
        EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO tg_analytics', current_schema());
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO tg_analytics', current_schema());
        REVOKE SELECT ON auth_sessions, oauth_states, calendar_links, push_subscriptions FROM tg_analytics;
    END IF;
END $$;

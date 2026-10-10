-- Places a user hearted ("Đã lưu", docs/ACCOUNTS.md §3): one row per user and place, kept with the account.
CREATE TABLE saved_places (
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    place_id text NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, place_id)
);
CREATE INDEX saved_places_recent ON saved_places (user_id, saved_at DESC);

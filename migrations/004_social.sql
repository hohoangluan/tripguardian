-- Home page library and friends (docs/ACCOUNTS.md §Bạn bè): nickname + bio on the account, saved places and themes,
-- friendships, direct messages that may carry one shared trip.
-- Unqualified names: the runner applies this in the connection's current schema (tests use a throwaway schema).

ALTER TABLE users ADD COLUMN nickname citext UNIQUE CHECK (nickname ~ '^[a-z0-9._]{3,24}$');
ALTER TABLE users ADD COLUMN bio text CHECK (length(bio) <= 160);
ALTER TABLE users ADD COLUMN last_active_at timestamptz;

CREATE TABLE saved_items (
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('place', 'theme')),
    item_id text NOT NULL CHECK (length(item_id) BETWEEN 1 AND 80),
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kind, item_id)
);

CREATE TABLE friendships (
    requester uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    addressee uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    accepted_at timestamptz,
    PRIMARY KEY (requester, addressee),
    CHECK (requester <> addressee)
);
CREATE INDEX friendships_addressee ON friendships (addressee);

CREATE TABLE messages (
    id bigserial PRIMARY KEY,
    sender uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    recipient uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    body text NOT NULL DEFAULT '' CHECK (length(body) <= 2000),
    journey_id text,
    imported_journey_id text,
    sent_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz,
    CHECK (body <> '' OR journey_id IS NOT NULL)
);
CREATE INDEX messages_pair ON messages (LEAST(sender, recipient), GREATEST(sender, recipient), id);
CREATE INDEX messages_unread ON messages (recipient) WHERE read_at IS NULL;
CREATE INDEX events_user_at ON events (user_id, at DESC) WHERE user_id IS NOT NULL;

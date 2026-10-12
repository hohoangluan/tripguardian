-- Guests: a visitor without a Google account is a users row with kind = 'guest' (docs/ACCOUNTS.md §Khách).
-- Unqualified names: the runner applies this in the connection's current schema (tests use a throwaway schema).

ALTER TABLE users ADD COLUMN kind text NOT NULL DEFAULT 'user' CHECK (kind IN ('user', 'guest'));
CREATE INDEX users_guests ON users (id) WHERE kind = 'guest';

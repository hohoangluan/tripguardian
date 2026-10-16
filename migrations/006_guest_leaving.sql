-- A guest whose page was closed (docs/ACCOUNTS.md §7): the session is marked when the browser reports the tab gone,
-- and deleted with the guest after a short wait unless the same guest shows up again (a reload).
-- Unqualified names: the runner applies this in the connection's current schema (tests use a throwaway schema).

ALTER TABLE auth_sessions ADD COLUMN leaving_at timestamptz;

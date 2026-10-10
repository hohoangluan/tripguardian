-- A guest is a users row with role 'guest' (no email, no Google id): it owns its one journey and its events, so ownership
-- checks and the Admin views work as for an account. Nothing about a guest is deleted (docs/ACCOUNTS.md §Khách).
ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('user', 'admin', 'guest'));

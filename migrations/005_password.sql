-- Email + password accounts next to Google (docs/ACCOUNTS.md §Đăng ký bằng email).
-- Unqualified names: the runner applies this in the connection's current schema (tests use a throwaway schema).

ALTER TABLE users ADD COLUMN password_hash text;

ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS password_salt TEXT;
ALTER TABLE manager_users ALTER COLUMN email DROP NOT NULL;

UPDATE manager_users
SET username = COALESCE(username, email),
    password_salt = COALESCE(password_salt, email)
WHERE username IS NULL OR password_salt IS NULL;

ALTER TABLE manager_users ALTER COLUMN username SET NOT NULL;
ALTER TABLE manager_users ALTER COLUMN password_salt SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS manager_users_username_idx ON manager_users (lower(username));

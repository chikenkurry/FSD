-- Existing guest sessions do not require email. Preserve legacy users and allow
-- many guests without an email; uniqueness only applies to supplied addresses.
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS email varchar(255) NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS users_email_nonempty ON public.users (lower(email)) WHERE email <> '';

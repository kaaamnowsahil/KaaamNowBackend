-- Roles granted to a user (Figma "How will you use KaaamNow?").
CREATE TABLE IF NOT EXISTS user_roles (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,
    role       VARCHAR(16) NOT NULL,
    status     VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_roles_user_role_uid UNIQUE (user_id, role),
    CONSTRAINT user_roles_role_chk CHECK (role IN ('business', 'worker', 'admin')),
    CONSTRAINT user_roles_status_chk CHECK (status IN ('active', 'suspended'))
);

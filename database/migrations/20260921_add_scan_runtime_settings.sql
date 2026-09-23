BEGIN;

CREATE TABLE IF NOT EXISTS public.scan_runtime_settings (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.scan_runtime_settings_audit (
    id bigserial PRIMARY KEY,
    old_configuration jsonb,
    new_configuration jsonb NOT NULL CHECK (jsonb_typeof(new_configuration) = 'object'),
    changed_at timestamptz NOT NULL DEFAULT now(),
    changed_by text NOT NULL
);

INSERT INTO public.scan_runtime_settings (id, configuration, updated_by)
VALUES (
    1,
    '{"incremental_polling_enabled":false,"dirty_parent_levels":1,"dirty_min_depth":3,"dirty_settle_seconds":60,"full_scan_time":"02:30","timezone":"Europe/Amsterdam","missed_full_scan_policy":"next_window","full_scan_window_minutes":30}'::jsonb,
    'migration'
)
ON CONFLICT (id) DO NOTHING;

COMMIT;

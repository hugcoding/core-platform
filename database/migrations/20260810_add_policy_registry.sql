-- SCRUM-92: minimal database-backed, immutable CORE policy snapshots.
BEGIN;

CREATE TABLE IF NOT EXISTS public.policy_versions (
    id uuid PRIMARY KEY,
    policy_code text NOT NULL CHECK (policy_code ~ '^[a-z][a-z0-9_]*$'),
    environment text NOT NULL CHECK (environment IN ('development', 'acceptance', 'production')),
    contract_version text NOT NULL,
    policy_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'approved', 'active', 'rejected', 'revoked')),
    configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    configuration_checksum text NOT NULL CHECK (configuration_checksum ~ '^[0-9a-f]{64}$'),
    effective_from timestamptz NOT NULL,
    effective_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    change_reason text NOT NULL,
    approved_at timestamptz,
    approved_by text,
    CHECK (effective_until IS NULL OR effective_until > effective_from),
    CHECK (status NOT IN ('approved', 'active') OR
           (approved_at IS NOT NULL AND approved_by IS NOT NULL)),
    UNIQUE (policy_code, environment, policy_version),
    UNIQUE (policy_code, environment, configuration_checksum),
    UNIQUE (policy_code, environment, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_resolution
    ON public.policy_versions(policy_code, environment, effective_from DESC, created_at DESC)
    WHERE status = 'active';

CREATE OR REPLACE FUNCTION public.reject_policy_version_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'policy_versions is append-only; insert a new policy snapshot';
END;
$$;

DROP TRIGGER IF EXISTS policy_versions_immutable ON public.policy_versions;
CREATE TRIGGER policy_versions_immutable
BEFORE UPDATE OR DELETE ON public.policy_versions
FOR EACH ROW EXECUTE FUNCTION public.reject_policy_version_mutation();

CREATE OR REPLACE VIEW public.v_current_policies AS
WITH eligible AS (
    SELECT p.*,
           row_number() OVER (
               PARTITION BY p.policy_code, p.environment
               ORDER BY p.effective_from DESC, p.created_at DESC, p.id DESC
           ) AS position
    FROM public.policy_versions p
    WHERE p.status = 'active'
      AND p.effective_from <= now()
      AND (p.effective_until IS NULL OR p.effective_until > now())
)
SELECT id, policy_code, environment, contract_version, policy_version,
       configuration, configuration_checksum, effective_from, effective_until,
       created_at, created_by, change_reason, approved_at, approved_by
FROM eligible
WHERE position = 1;

COMMENT ON TABLE public.policy_versions IS
    'Immutable, environment-scoped CORE business-policy snapshots; changes require a new version.';
COMMENT ON VIEW public.v_current_policies IS
    'Deterministically resolves the newest effective active policy per code and OAP environment.';

COMMIT;

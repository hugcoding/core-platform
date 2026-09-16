BEGIN;
SET LOCAL lock_timeout = '2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_source_documents) OR EXISTS(SELECT 1 FROM finance.finance_accounts)
 OR EXISTS(SELECT 1 FROM finance.finance_ingest_jobs) OR EXISTS(SELECT 1 FROM finance.finance_counterparties) THEN
 RAISE EXCEPTION 'finance_rollback_refused_populated_use_forward_fix'; END IF;
END $$;
DROP SCHEMA finance CASCADE;
-- Roles are retained: other deployments may use them. No existing CORE data removed.
COMMIT;

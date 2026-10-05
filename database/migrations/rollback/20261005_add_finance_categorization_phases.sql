BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_ingest_jobs WHERE job_kind='categorize' AND status IN ('pending','running'))
 THEN RAISE EXCEPTION 'finance_categorization_active'; END IF;
END $$;
ALTER TABLE finance.finance_ingest_jobs DROP COLUMN categorization_cursor, DROP COLUMN categorization_phase;
COMMIT;

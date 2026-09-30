BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_ingest_jobs WHERE job_kind='recurring')
 OR EXISTS(SELECT 1 FROM finance.finance_recurring_patterns)
 OR EXISTS(SELECT 1 FROM finance.finance_recurring_scans) THEN
  RAISE EXCEPTION 'finance_recurring_history_present'; END IF;
END $$;
DROP INDEX finance.finance_recurring_source_lookup;
DROP INDEX finance.finance_recurring_import_lookup;
DROP TABLE finance.finance_recurring_members;
DROP TABLE finance.finance_recurring_detections;
DROP TABLE finance.finance_recurring_patterns;
DROP TABLE finance.finance_recurring_scans;
DROP FUNCTION finance.validate_recurring_member();
DROP FUNCTION finance.validate_recurring_detection();
ALTER TABLE finance.finance_ingest_jobs DROP CONSTRAINT finance_ingest_jobs_job_kind_check;
ALTER TABLE finance.finance_ingest_jobs ADD CONSTRAINT finance_ingest_jobs_job_kind_check
 CHECK(job_kind IN ('import','balances','references','categorize'));
COMMIT;

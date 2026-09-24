BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_reference_extractions)
 OR EXISTS(SELECT 1 FROM finance.finance_record_bank_references)
 OR EXISTS(SELECT 1 FROM finance.finance_ingest_jobs WHERE job_kind='references') THEN
  RAISE EXCEPTION 'finance_bank_reference_history_present';
 END IF;
END $$;
ALTER TABLE finance.finance_ingest_jobs DROP CONSTRAINT finance_ingest_jobs_job_kind_check;
ALTER TABLE finance.finance_ingest_jobs ADD CONSTRAINT finance_ingest_jobs_job_kind_check CHECK(job_kind IN ('import','balances'));
DROP TABLE finance.finance_record_bank_references;
DROP FUNCTION finance.validate_bank_reference();
DROP TABLE finance.finance_reference_extractions;
COMMIT;

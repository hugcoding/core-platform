BEGIN;
SET LOCAL lock_timeout='2s';
ALTER TABLE finance.finance_ingest_jobs
 ADD COLUMN categorization_phase text NOT NULL DEFAULT 'core' CHECK (categorization_phase IN ('core','llm')),
 ADD COLUMN categorization_cursor uuid;
COMMIT;

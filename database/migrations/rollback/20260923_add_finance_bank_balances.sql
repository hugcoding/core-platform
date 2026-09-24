BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_balance_extractions) OR EXISTS(SELECT 1 FROM finance.finance_bank_balances)
 OR EXISTS(SELECT 1 FROM finance.finance_ingest_jobs WHERE job_kind='balances') THEN
  RAISE EXCEPTION 'finance_balance_history_present';
 END IF;
END $$;
DROP TABLE finance.finance_bank_balances;
DROP TABLE finance.finance_balance_extractions;
ALTER TABLE finance.finance_ingest_jobs DROP COLUMN job_kind;
COMMIT;

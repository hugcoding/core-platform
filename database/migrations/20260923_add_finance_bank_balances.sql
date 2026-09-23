-- Append-only bank evidence. No transaction, classification or source rewrites.
BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF to_regclass('finance.finance_transaction_types') IS NULL OR to_regclass('finance.v_account_groups') IS NULL THEN
  RAISE EXCEPTION 'finance_prior_classification_and_group_migrations_required';
 END IF;
END $$;
ALTER TABLE finance.finance_ingest_jobs ADD COLUMN job_kind text NOT NULL DEFAULT 'import'
 CHECK(job_kind IN ('import','balances'));
CREATE TABLE finance.finance_balance_extractions (
 batch_id uuid PRIMARY KEY REFERENCES finance.finance_import_batches(id),
 extractor_version text NOT NULL CHECK(extractor_version='camt-balances-v1'),
 status text NOT NULL CHECK(status IN ('extracted','unavailable')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_bank_balances (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 batch_id uuid NOT NULL REFERENCES finance.finance_balance_extractions(batch_id),
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 locator text NOT NULL CHECK(locator ~ '^stmt:[1-9][0-9]*$'),
 private_data text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(batch_id,locator)
);
CREATE INDEX finance_bank_balances_account ON finance.finance_bank_balances(account_id);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['finance_balance_extractions','finance_bank_balances'] LOOP
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.%I FOR EACH ROW EXECUTE FUNCTION finance.immutable()',t);
 EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.%I FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable()',t);
 END LOOP;
END $$;
GRANT SELECT ON finance.finance_balance_extractions,finance.finance_bank_balances TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_balance_extractions,finance.finance_bank_balances TO core_finance_ingest;
COMMIT;

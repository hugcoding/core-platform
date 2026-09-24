-- Stable ASN NtryRef evidence, without rewriting sources or prior decisions.
BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF to_regclass('finance.finance_balance_extractions') IS NULL THEN
  RAISE EXCEPTION 'finance_bank_balances_migration_required';
 END IF;
END $$;
CREATE TABLE finance.finance_reference_extractions (
 batch_id uuid PRIMARY KEY REFERENCES finance.finance_import_batches(id),
 version text NOT NULL CHECK(version='asn-ntryref-v1'),
 status text NOT NULL CHECK(status IN ('indexed','unavailable')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_record_bank_references (
 record_id uuid PRIMARY KEY REFERENCES finance.finance_import_records(id),
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 profile text NOT NULL CHECK(profile='asn-ntryref-v1'),
 identity_key text NOT NULL CHECK(identity_key ~ '^[a-f0-9]{64}$'),
 private_data text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finance_bank_reference_identity ON finance.finance_record_bank_references(account_id,identity_key);
CREATE FUNCTION finance.validate_bank_reference() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM finance.finance_import_records r WHERE r.id=NEW.record_id AND r.account_id=NEW.account_id) THEN
  RAISE EXCEPTION 'finance_bank_reference_account_mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_bank_reference BEFORE INSERT ON finance.finance_record_bank_references
 FOR EACH ROW EXECUTE FUNCTION finance.validate_bank_reference();
REVOKE ALL ON FUNCTION finance.validate_bank_reference() FROM PUBLIC;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['finance_reference_extractions','finance_record_bank_references'] LOOP
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.%I FOR EACH ROW EXECUTE FUNCTION finance.immutable()',t);
 EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.%I FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable()',t);
 END LOOP;
END $$;
GRANT SELECT ON finance.finance_reference_extractions,finance.finance_record_bank_references TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_reference_extractions,finance.finance_record_bank_references TO core_finance_ingest;
ALTER TABLE finance.finance_ingest_jobs DROP CONSTRAINT finance_ingest_jobs_job_kind_check;
ALTER TABLE finance.finance_ingest_jobs ADD CONSTRAINT finance_ingest_jobs_job_kind_check
 CHECK(job_kind IN ('import','balances','references'));
COMMIT;

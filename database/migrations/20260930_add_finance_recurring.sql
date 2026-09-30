-- SCRUM-160 slice 1: derived evidence, never transactions/classification.
BEGIN;
SET LOCAL lock_timeout='2s';
-- Support the existing active-source view during account scans/member lookups.
CREATE INDEX finance_recurring_source_lookup ON finance.finance_transaction_sources(transaction_id);
CREATE INDEX finance_recurring_import_lookup ON finance.finance_import_events(batch_id,id DESC);
ALTER TABLE finance.finance_ingest_jobs DROP CONSTRAINT finance_ingest_jobs_job_kind_check;
ALTER TABLE finance.finance_ingest_jobs ADD CONSTRAINT finance_ingest_jobs_job_kind_check
 CHECK(job_kind IN ('import','balances','references','categorize','recurring'));
CREATE TABLE finance.finance_recurring_patterns (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 identity_key text NOT NULL UNIQUE CHECK(identity_key ~ '^[a-f0-9]{64}$'),
 direction text NOT NULL CHECK(direction IN ('debit','credit')),
 currency text NOT NULL CHECK(currency ~ '^[A-Z]{3}$'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finance_recurring_account ON finance.finance_recurring_patterns(account_id,id);
CREATE TABLE finance.finance_recurring_detections (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 pattern_id uuid NOT NULL REFERENCES finance.finance_recurring_patterns(id),
 job_id uuid NOT NULL REFERENCES finance.finance_ingest_jobs(id),
 evidence_key text NOT NULL CHECK(evidence_key ~ '^[a-f0-9]{64}$'),
 active boolean NOT NULL,
 cadence text CHECK(cadence IN ('weekly','monthly','quarterly','yearly')),
 confidence numeric(4,3) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 observation_count integer NOT NULL CHECK(observation_count >= 0),
 private_data text NOT NULL, detection_version text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), created_tx bigint NOT NULL DEFAULT txid_current(),
 UNIQUE(pattern_id,job_id), CHECK(NOT active OR (cadence IS NOT NULL AND observation_count >= 3))
);
CREATE INDEX finance_recurring_latest ON finance.finance_recurring_detections(pattern_id,sequence_no DESC);
CREATE TABLE finance.finance_recurring_members (
 detection_id uuid NOT NULL REFERENCES finance.finance_recurring_detections(id),
 transaction_id uuid NOT NULL REFERENCES finance.finance_transactions(id),
 PRIMARY KEY(detection_id,transaction_id)
);
CREATE TABLE finance.finance_recurring_scans (
 job_id uuid NOT NULL REFERENCES finance.finance_ingest_jobs(id),
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 revision_key text NOT NULL CHECK(revision_key ~ '^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(job_id,account_id)
);
CREATE INDEX finance_recurring_revision ON finance.finance_recurring_scans(account_id,revision_key);
CREATE INDEX finance_recurring_scan_latest ON finance.finance_recurring_scans(account_id,created_at DESC,job_id DESC);
CREATE FUNCTION finance.validate_recurring_member() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM finance.finance_recurring_detections d
   JOIN finance.finance_recurring_patterns p ON p.id=d.pattern_id
   JOIN finance.finance_transactions t ON t.id=NEW.transaction_id
   WHERE d.id=NEW.detection_id AND d.created_tx=txid_current()
     AND t.account_id=p.account_id AND t.currency=p.currency
     AND CASE WHEN p.direction='debit' THEN t.amount<0 ELSE t.amount>0 END) THEN
   RAISE EXCEPTION 'finance_recurring_member_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_recurring_member BEFORE INSERT ON finance.finance_recurring_members
 FOR EACH ROW EXECUTE FUNCTION finance.validate_recurring_member();
CREATE FUNCTION finance.validate_recurring_detection() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM finance.finance_ingest_jobs WHERE id=NEW.job_id AND job_kind='recurring')
 OR NEW.observation_count<>(SELECT count(*) FROM finance.finance_recurring_members WHERE detection_id=NEW.id) THEN
   RAISE EXCEPTION 'finance_recurring_evidence_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER validate_recurring_detection AFTER INSERT ON finance.finance_recurring_detections
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION finance.validate_recurring_detection();
REVOKE ALL ON FUNCTION finance.validate_recurring_member(),finance.validate_recurring_detection() FROM PUBLIC;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['finance_recurring_patterns','finance_recurring_detections','finance_recurring_members','finance_recurring_scans'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.%I FOR EACH ROW EXECUTE FUNCTION finance.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.%I FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable()',t);
  EXECUTE format('GRANT SELECT ON finance.%I TO core_finance_api,core_finance_ingest',t);
  EXECUTE format('GRANT INSERT ON finance.%I TO core_finance_ingest',t);
 END LOOP;
END $$;
GRANT USAGE ON SEQUENCE finance.finance_recurring_detections_sequence_no_seq TO core_finance_ingest;
COMMIT;

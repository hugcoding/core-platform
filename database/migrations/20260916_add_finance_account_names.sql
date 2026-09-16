-- Apply after 20260916_add_finance_mvp.sql. Does not change bank identities.
BEGIN;
SET LOCAL lock_timeout = '2s';
CREATE TABLE finance.finance_account_name_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 private_data text NOT NULL,
 supersedes_event_id uuid UNIQUE REFERENCES finance.finance_account_name_events(id),
 actor text NOT NULL,
 idempotency_key uuid NOT NULL UNIQUE,
 payload_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX finance_account_name_first_event
 ON finance.finance_account_name_events(account_id) WHERE supersedes_event_id IS NULL;
CREATE INDEX finance_account_name_latest
 ON finance.finance_account_name_events(account_id,sequence_no DESC);
CREATE FUNCTION finance.validate_account_name_predecessor() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.supersedes_event_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM finance.finance_account_name_events e
  WHERE e.id=NEW.supersedes_event_id AND e.account_id=NEW.account_id
 ) THEN RAISE EXCEPTION 'finance_account_name_predecessor_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_predecessor BEFORE INSERT ON finance.finance_account_name_events
 FOR EACH ROW EXECUTE FUNCTION finance.validate_account_name_predecessor();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_account_name_events
 FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_account_name_events
 FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
REVOKE ALL ON finance.finance_account_name_events FROM PUBLIC;
REVOKE ALL ON FUNCTION finance.validate_account_name_predecessor() FROM PUBLIC;
GRANT SELECT,INSERT ON finance.finance_account_name_events TO core_finance_api;
GRANT USAGE ON SEQUENCE finance.finance_account_name_events_sequence_no_seq TO core_finance_api;
COMMIT;

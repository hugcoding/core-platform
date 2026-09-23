-- SCRUM-157. Account metadata is independent of immutable bank identity/reviews.
BEGIN;
SET LOCAL lock_timeout='2s';
CREATE TABLE finance.finance_wealth_groups (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_wealth_group_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 group_id uuid NOT NULL REFERENCES finance.finance_wealth_groups(id), private_data text NOT NULL,
 supersedes_event_id uuid UNIQUE REFERENCES finance.finance_wealth_group_events(id),
 actor text NOT NULL, idempotency_key uuid NOT NULL UNIQUE, payload_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX finance_group_first ON finance.finance_wealth_group_events(group_id) WHERE supersedes_event_id IS NULL;
CREATE INDEX finance_group_latest ON finance.finance_wealth_group_events(group_id,sequence_no DESC);
CREATE TABLE finance.finance_account_group_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 group_id uuid REFERENCES finance.finance_wealth_groups(id),
 relationship text NOT NULL CHECK (
   (group_id IS NULL AND relationship='UNASSIGNED') OR
   (group_id IS NOT NULL AND relationship IN ('OWN','JOINT','MANAGED'))),
 name_event_id uuid REFERENCES finance.finance_account_name_events(id),
 supersedes_event_id uuid UNIQUE REFERENCES finance.finance_account_group_events(id),
 actor text NOT NULL, idempotency_key uuid NOT NULL UNIQUE, payload_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX finance_account_group_first ON finance.finance_account_group_events(account_id) WHERE supersedes_event_id IS NULL;
CREATE INDEX finance_account_group_latest ON finance.finance_account_group_events(account_id,sequence_no DESC);
CREATE FUNCTION finance.validate_group_predecessor() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_TABLE_NAME='finance_wealth_group_events' THEN
  IF NEW.supersedes_event_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM finance.finance_wealth_group_events e WHERE e.id=NEW.supersedes_event_id AND e.group_id=NEW.group_id
  ) THEN RAISE EXCEPTION 'finance_group_predecessor_mismatch'; END IF;
 ELSE
  IF NEW.supersedes_event_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM finance.finance_account_group_events e WHERE e.id=NEW.supersedes_event_id AND e.account_id=NEW.account_id
  ) THEN RAISE EXCEPTION 'finance_membership_predecessor_mismatch'; END IF;
  IF NEW.name_event_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM finance.finance_account_name_events n WHERE n.id=NEW.name_event_id AND n.account_id=NEW.account_id
  ) THEN RAISE EXCEPTION 'finance_membership_name_mismatch'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_predecessor BEFORE INSERT ON finance.finance_wealth_group_events
 FOR EACH ROW EXECUTE FUNCTION finance.validate_group_predecessor();
CREATE TRIGGER validate_predecessor BEFORE INSERT ON finance.finance_account_group_events
 FOR EACH ROW EXECUTE FUNCTION finance.validate_group_predecessor();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['finance_wealth_groups','finance_wealth_group_events','finance_account_group_events'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.%I FOR EACH ROW EXECUTE FUNCTION finance.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.%I FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable()',t);
 END LOOP;
END $$;
CREATE VIEW finance.v_account_groups AS
 SELECT a.id AS account_id,e.id AS group_event_id,e.group_id,coalesce(e.relationship,'UNASSIGNED') AS relationship
 FROM finance.finance_accounts a LEFT JOIN LATERAL (
  SELECT id,group_id,relationship FROM finance.finance_account_group_events
  WHERE account_id=a.id ORDER BY sequence_no DESC LIMIT 1
 ) e ON true;
REVOKE ALL ON FUNCTION finance.validate_group_predecessor() FROM PUBLIC;
GRANT SELECT,INSERT ON finance.finance_wealth_groups,finance.finance_wealth_group_events,finance.finance_account_group_events TO core_finance_api;
GRANT SELECT ON finance.v_account_groups TO core_finance_api;
GRANT USAGE ON SEQUENCE finance.finance_wealth_group_events_sequence_no_seq,finance.finance_account_group_events_sequence_no_seq TO core_finance_api;
COMMIT;

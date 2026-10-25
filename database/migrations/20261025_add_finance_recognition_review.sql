BEGIN;
SET LOCAL lock_timeout='2s';
CREATE TABLE finance.finance_recognition_rule_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 rule_id uuid NOT NULL,
 sequence_no bigserial UNIQUE NOT NULL,
 private_data text NOT NULL,
 active boolean NOT NULL,
 merchant_id uuid REFERENCES finance.finance_counterparties(id),
 supersedes_event_id uuid REFERENCES finance.finance_recognition_rule_events(id),
 idempotency_key uuid UNIQUE NOT NULL,
 payload_digest text NOT NULL,
 applied_count integer NOT NULL DEFAULT 0 CHECK(applied_count>=0),
 actor text NOT NULL DEFAULT 'owner' CHECK(actor='owner'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finance_recognition_rule_current ON finance.finance_recognition_rule_events(rule_id,sequence_no DESC);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_recognition_rule_events FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_recognition_rule_events FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
CREATE FUNCTION finance.validate_recognition_rule() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE latest uuid;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('finance-category-learning'));
 SELECT id INTO latest FROM finance.finance_recognition_rule_events WHERE rule_id=NEW.rule_id ORDER BY sequence_no DESC LIMIT 1;
 IF NEW.supersedes_event_id IS DISTINCT FROM latest THEN RAISE EXCEPTION 'finance_recognition_rule_changed'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_recognition_rule BEFORE INSERT ON finance.finance_recognition_rule_events FOR EACH ROW EXECUTE FUNCTION finance.validate_recognition_rule();
GRANT SELECT ON finance.finance_recognition_rule_events TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_recognition_rule_events TO core_finance_api;
GRANT USAGE,SELECT ON SEQUENCE finance.finance_recognition_rule_events_sequence_no_seq TO core_finance_api;
REVOKE ALL ON FUNCTION finance.validate_recognition_rule() FROM PUBLIC;
ALTER TABLE finance.finance_review_events ADD COLUMN recognition_rule_event_id uuid REFERENCES finance.finance_recognition_rule_events(id);
CREATE OR REPLACE FUNCTION finance.protect_local_classification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF current_user='core_finance_ingest' OR NEW.actor='finance-local' THEN
  PERFORM pg_advisory_xact_lock(hashtext('finance-category-learning'));
  IF NEW.model_version='finance-local-v1:owner-rule-v1' THEN
   IF NEW.actor<>'finance-local' OR NEW.classification_source IS DISTINCT FROM 'RULE'
    OR NEW.transaction_type IS NULL OR NEW.transaction_type NOT IN ('INCOME','EXPENSE','TAX','CORRECTION','UNKNOWN')
    OR NEW.confirmed IS DISTINCT FROM false OR NEW.source_review_id IS NOT NULL OR NEW.suggestion_method IS NOT NULL
    OR NOT EXISTS(SELECT 1 FROM finance.finance_recognition_rule_events e
      WHERE e.id=NEW.recognition_rule_event_id AND e.active
      AND (e.merchant_id IS NULL OR e.merchant_id IS NOT DISTINCT FROM NEW.merchant_id)
      AND NOT EXISTS(SELECT 1 FROM finance.finance_recognition_rule_events newer WHERE newer.rule_id=e.rule_id AND newer.sequence_no>e.sequence_no))
    OR EXISTS(SELECT 1 FROM finance.finance_review_events WHERE transaction_id=NEW.transaction_id AND coalesce(confirmed,true))
   THEN RAISE EXCEPTION 'finance_invalid_owner_rule'; END IF;
   RETURN NEW;
  END IF;
  IF NEW.actor<>'finance-local' OR NEW.classification_source NOT IN ('AI','MERCHANT','RULE')
   OR NEW.classification_source IS NULL OR NEW.confirmed IS DISTINCT FROM false
   OR NEW.model_version IS NULL OR NEW.model_version NOT LIKE 'finance-local-v1:%'
   OR NEW.category_code IS NULL THEN RAISE EXCEPTION 'finance_invalid_automatic_classification'; END IF;
  IF NEW.classification_source='RULE' AND (
   NEW.model_version NOT IN ('finance-local-v1:core-rule-v1:groceries','finance-local-v1:core-rule-v1:transport',
    'finance-local-v1:core-rule-v1:dining','finance-local-v1:core-rule-v1:utilities',
    'finance-local-v1:core-rule-v1:subscriptions','finance-local-v1:core-rule-v1:insurance',
    'finance-local-v1:core-rule-v1:clothing','finance-local-v1:core-rule-v1:household',
    'finance-local-v1:core-rule-v1:bank_interest','finance-local-v1:core-rule-v1:bank_costs','finance-local-v1:core-rule-v1:benefit','finance-local-v1:core-rule-v1:known_account_transfer','finance-local-v1:core-rule-v1:salary','finance-local-v1:core-rule-v1:asn-interest-6607')
   OR NEW.source_review_id IS NOT NULL OR NEW.suggestion_method IS NOT NULL
  ) THEN RAISE EXCEPTION 'finance_invalid_local_rule'; END IF;
  IF NEW.model_version='finance-local-v1:core-rule-v1:known_account_transfer' AND
   (NEW.transaction_type IS DISTINCT FROM 'TRANSFER' OR NEW.category_code IS DISTINCT FROM 'overboekingen' OR NEW.subcategory_code IS NOT NULL OR NEW.merchant_id IS NOT NULL)
  THEN RAISE EXCEPTION 'finance_invalid_transfer_rule'; END IF;
  IF NEW.model_version='finance-local-v1:core-rule-v1:salary' AND (NEW.transaction_type IS DISTINCT FROM 'INCOME' OR NEW.category_code IS DISTINCT FROM 'inkomen' OR NEW.subcategory_code IS DISTINCT FROM 'inkomen_salaris') THEN RAISE EXCEPTION 'finance_invalid_salary_rule'; END IF;
  IF NEW.model_version='finance-local-v1:core-rule-v1:asn-interest-6607' AND (NEW.transaction_type IS DISTINCT FROM 'INCOME' OR NEW.category_code IS DISTINCT FROM 'inkomen' OR NEW.subcategory_code IS DISTINCT FROM 'inkomen_rente' OR NEW.merchant_id IS NOT NULL) THEN RAISE EXCEPTION 'finance_invalid_asn_interest_rule'; END IF;
  IF EXISTS(SELECT 1 FROM finance.finance_review_events WHERE transaction_id=NEW.transaction_id
    AND coalesce(confirmed,true)) THEN RAISE EXCEPTION 'finance_owner_review_protected'; END IF;
 END IF;
 RETURN NEW;
END $$;
COMMIT;

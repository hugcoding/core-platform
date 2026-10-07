BEGIN;
SET LOCAL lock_timeout='2s';
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_suggestion_evidence,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
 (source_review_id IS NULL AND suggestion_method IS NULL) OR
 (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL AND suggestion_method IN ('local-merchant-v1','local-merchant-v2','local-merchant-v3','local-merchant-v4')));
CREATE OR REPLACE FUNCTION finance.protect_local_classification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF current_user='core_finance_ingest' OR NEW.actor='finance-local' THEN
  PERFORM pg_advisory_xact_lock(hashtext('finance-category-learning'));
  IF NEW.actor<>'finance-local' OR NEW.classification_source NOT IN ('AI','MERCHANT','RULE')
   OR NEW.classification_source IS NULL OR NEW.confirmed IS DISTINCT FROM false
   OR NEW.model_version IS NULL OR NEW.model_version NOT LIKE 'finance-local-v1:%'
   OR NEW.category_code IS NULL THEN RAISE EXCEPTION 'finance_invalid_automatic_classification'; END IF;
  IF NEW.classification_source='RULE' AND (
   NEW.model_version NOT IN ('finance-local-v1:core-rule-v1:groceries','finance-local-v1:core-rule-v1:transport',
    'finance-local-v1:core-rule-v1:dining','finance-local-v1:core-rule-v1:utilities',
    'finance-local-v1:core-rule-v1:subscriptions','finance-local-v1:core-rule-v1:insurance',
    'finance-local-v1:core-rule-v1:clothing','finance-local-v1:core-rule-v1:household',
    'finance-local-v1:core-rule-v1:bank_interest','finance-local-v1:core-rule-v1:bank_costs','finance-local-v1:core-rule-v1:benefit')
   OR NEW.source_review_id IS NOT NULL OR NEW.suggestion_method IS NOT NULL
  ) THEN RAISE EXCEPTION 'finance_invalid_local_rule'; END IF;
  IF EXISTS(SELECT 1 FROM finance.finance_review_events WHERE transaction_id=NEW.transaction_id
    AND coalesce(confirmed,true)) THEN RAISE EXCEPTION 'finance_owner_review_protected'; END IF;
 END IF;
 RETURN NEW;
END $$;
COMMIT;

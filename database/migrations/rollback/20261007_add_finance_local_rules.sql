BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_review_events WHERE (actor='finance-local' AND classification_source='RULE') OR suggestion_method='local-merchant-v4') THEN RAISE EXCEPTION 'finance_local_rule_history_present'; END IF;
END $$;
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_suggestion_evidence,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
 (source_review_id IS NULL AND suggestion_method IS NULL) OR
 (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL AND suggestion_method IN ('local-merchant-v1','local-merchant-v2','local-merchant-v3')));
CREATE OR REPLACE FUNCTION finance.protect_local_classification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF current_user='core_finance_ingest' OR NEW.actor='finance-local' THEN
  PERFORM pg_advisory_xact_lock(hashtext('finance-category-learning'));
  IF NEW.actor<>'finance-local' OR NEW.classification_source NOT IN ('AI','MERCHANT')
   OR NEW.classification_source IS NULL OR NEW.confirmed IS DISTINCT FROM false
   OR NEW.model_version IS NULL OR NEW.model_version NOT LIKE 'finance-local-v1:%'
   OR NEW.category_code IS NULL THEN RAISE EXCEPTION 'finance_invalid_automatic_classification'; END IF;
  IF EXISTS(SELECT 1 FROM finance.finance_review_events WHERE transaction_id=NEW.transaction_id
    AND coalesce(confirmed,true)) THEN RAISE EXCEPTION 'finance_owner_review_protected'; END IF;
 END IF;
 RETURN NEW;
END $$;
COMMIT;

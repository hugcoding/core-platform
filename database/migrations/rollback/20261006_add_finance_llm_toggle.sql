BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_classification_settings_events)
 OR EXISTS(SELECT 1 FROM finance.finance_review_events WHERE suggestion_method='local-merchant-v3') THEN
  RAISE EXCEPTION 'finance_classification_settings_history_present';
 END IF;
END $$;
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_suggestion_evidence,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
 (source_review_id IS NULL AND suggestion_method IS NULL) OR
 (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL AND suggestion_method IN ('local-merchant-v1','local-merchant-v2')));
DROP VIEW finance.v_classification_settings;
DROP TABLE finance.finance_classification_settings_events;
COMMIT;

BEGIN;
SET LOCAL lock_timeout = '2s';
LOCK TABLE finance.finance_review_events IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_review_events WHERE source_review_id IS NOT NULL) THEN
  RAISE EXCEPTION 'finance_suggestion_rollback_refused_preserve_evidence';
 END IF;
END $$;
DROP TRIGGER validate_suggestion_evidence ON finance.finance_review_events;
DROP FUNCTION finance.validate_suggestion_evidence();
ALTER TABLE finance.finance_review_events
 DROP CONSTRAINT finance_suggestion_evidence,
 DROP COLUMN source_review_id, DROP COLUMN suggestion_method;
COMMIT;

BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN IF EXISTS(SELECT 1 FROM finance.finance_recurring_reviews) THEN
 RAISE EXCEPTION 'finance_recurring_reviews_rollback_requires_empty_history'; END IF; END $$;
DROP TABLE finance.finance_recurring_reviews;
DROP FUNCTION finance.validate_recurring_review();
COMMIT;

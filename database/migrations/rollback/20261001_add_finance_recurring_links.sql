BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN IF EXISTS(SELECT 1 FROM finance.finance_recurring_links) THEN
 RAISE EXCEPTION 'finance_recurring_links_rollback_requires_empty_history'; END IF; END $$;
DROP VIEW finance.v_recurring_membership;
DROP TABLE finance.finance_recurring_links;
DROP FUNCTION finance.validate_recurring_link();
COMMIT;

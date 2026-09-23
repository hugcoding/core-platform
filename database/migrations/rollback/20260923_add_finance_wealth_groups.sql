BEGIN;
SET LOCAL lock_timeout='2s';
LOCK TABLE finance.finance_wealth_groups,finance.finance_wealth_group_events,finance.finance_account_group_events IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_wealth_groups) OR EXISTS(SELECT 1 FROM finance.finance_wealth_group_events)
 OR EXISTS(SELECT 1 FROM finance.finance_account_group_events) THEN
  RAISE EXCEPTION 'finance_groups_rollback_refused_preserve_history';
 END IF;
END $$;
DROP VIEW finance.v_account_groups;
DROP TABLE finance.finance_account_group_events;
DROP TABLE finance.finance_wealth_group_events;
DROP TABLE finance.finance_wealth_groups;
DROP FUNCTION finance.validate_group_predecessor();
COMMIT;

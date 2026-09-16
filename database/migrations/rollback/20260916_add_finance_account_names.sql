-- Empty-only schema rollback. Never erase recorded name changes.
BEGIN;
SET LOCAL lock_timeout = '2s';
LOCK TABLE finance.finance_account_name_events IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_account_name_events) THEN
  RAISE EXCEPTION 'finance_account_names_rollback_refused_populated';
 END IF;
END $$;
DROP TABLE finance.finance_account_name_events;
DROP FUNCTION finance.validate_account_name_predecessor();
COMMIT;

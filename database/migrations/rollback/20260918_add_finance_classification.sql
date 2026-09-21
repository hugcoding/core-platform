BEGIN;
SET LOCAL lock_timeout='2s';
LOCK TABLE finance.finance_review_events,finance.finance_categories,finance.finance_category_events IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_review_events WHERE transaction_type IS NOT NULL OR subcategory_code IS NOT NULL
 OR merchant_id IS NOT NULL OR classification_source IS NOT NULL OR confidence IS NOT NULL OR confirmed IS NOT NULL
 OR model_version IS NOT NULL OR transfer_id IS NOT NULL OR linked_transaction_id IS NOT NULL OR transfer_status IS NOT NULL)
 OR EXISTS(SELECT 1 FROM finance.finance_review_events r WHERE category_code IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM finance.finance_category_baseline b WHERE b.code=r.category_code))
 OR EXISTS(SELECT 1 FROM finance.finance_category_events) THEN
 RAISE EXCEPTION 'finance_classification_rollback_refused_preserve_history'; END IF;
END $$;
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_suggestion_evidence,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
 (source_review_id IS NULL AND suggestion_method IS NULL) OR
 (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL AND suggestion_method='local-merchant-v1'));
DROP VIEW finance.v_transactions;
DROP INDEX finance.finance_review_current;
DROP TRIGGER validate_classification ON finance.finance_review_events;
DROP FUNCTION finance.validate_classification();
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_transfer_not_self,
 DROP COLUMN transaction_type,DROP COLUMN subcategory_code,DROP COLUMN merchant_id,
 DROP COLUMN classification_source,DROP COLUMN confidence,DROP COLUMN confirmed,DROP COLUMN model_version,
 DROP COLUMN transfer_id,DROP COLUMN linked_transaction_id,DROP COLUMN transfer_status;
DROP TRIGGER category_change ON finance.finance_categories;
DROP TRIGGER category_audit ON finance.finance_categories;
DROP FUNCTION finance.category_change();
DROP FUNCTION finance.category_audit();
DROP TABLE finance.finance_category_events;
DELETE FROM finance.finance_categories WHERE parent_id IS NOT NULL;
DELETE FROM finance.finance_categories c WHERE NOT EXISTS(SELECT 1 FROM finance.finance_category_baseline b WHERE b.code=c.code);
UPDATE finance.finance_categories c SET name=b.label FROM finance.finance_category_baseline b WHERE b.code=c.code;
ALTER TABLE finance.finance_categories DROP CONSTRAINT finance_category_not_self,DROP CONSTRAINT finance_category_name,
 DROP COLUMN parent_id,DROP COLUMN id,DROP COLUMN label,DROP COLUMN transaction_type,DROP COLUMN active,
 DROP COLUMN sort_order,DROP COLUMN is_system,DROP COLUMN created_at,DROP COLUMN updated_at;
ALTER TABLE finance.finance_categories RENAME COLUMN name TO label;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_categories FOR EACH ROW EXECUTE FUNCTION finance.immutable();
REVOKE INSERT ON finance.finance_counterparties FROM core_finance_api;
DROP TABLE finance.finance_category_baseline;
DROP TABLE finance.finance_transaction_types;
CREATE VIEW finance.v_transactions AS
 SELECT t.*, review.category_code,review.id AS review_id FROM finance.finance_transactions t
 LEFT JOIN LATERAL (SELECT id,category_code FROM finance.finance_review_events WHERE transaction_id=t.id ORDER BY sequence_no DESC LIMIT 1) review ON true
 WHERE EXISTS(SELECT 1 FROM finance.finance_transaction_sources s JOIN finance.finance_import_records r ON r.id=s.record_id
 JOIN finance.v_import_status b ON b.id=r.batch_id WHERE s.transaction_id=t.id AND b.status IN ('imported','partial'));
GRANT SELECT ON finance.v_transactions TO core_finance_api,core_finance_ingest;
COMMIT;

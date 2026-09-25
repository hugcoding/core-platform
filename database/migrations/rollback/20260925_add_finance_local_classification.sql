BEGIN;
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM finance.finance_ingest_jobs WHERE job_kind='categorize')
 OR EXISTS(SELECT 1 FROM finance.finance_review_events WHERE actor='finance-local') THEN
  RAISE EXCEPTION 'finance_local_classification_history_present'; END IF;
END $$;
CREATE OR REPLACE VIEW finance.v_transactions AS
 SELECT t.*,review.category_code,review.id AS review_id,
 coalesce(review.transaction_type,'UNKNOWN') AS transaction_type,review.subcategory_code,review.merchant_id,
 coalesce(review.classification_source,CASE WHEN review.id IS NULL THEN NULL WHEN review.source_review_id IS NULL THEN 'MANUAL' ELSE 'MERCHANT' END) AS classification_source,
 review.confidence,coalesce(review.confirmed,review.id IS NOT NULL) AS confirmed,
 review.created_at AS classified_at,review.suggestion_method AS rule_version,review.model_version,
 review.source_review_id AS rule_review_id,review.transfer_id,review.linked_transaction_id,
 coalesce(review.transfer_status,'UNMATCHED') AS transfer_status,merchant.private_data AS merchant_data,
 (review.id IS NOT NULL AND review.transaction_type IS NULL) AS legacy_classification
 FROM finance.finance_transactions t
 LEFT JOIN LATERAL (SELECT * FROM finance.finance_review_events WHERE transaction_id=t.id
   AND coalesce(confirmed,true) ORDER BY sequence_no DESC LIMIT 1) review ON true
 LEFT JOIN finance.finance_counterparties merchant ON merchant.id=review.merchant_id
 WHERE EXISTS(SELECT 1 FROM finance.finance_transaction_sources s JOIN finance.finance_import_records r ON r.id=s.record_id
 JOIN finance.v_import_status b ON b.id=r.batch_id WHERE s.transaction_id=t.id AND b.status IN ('imported','partial'));
REVOKE SELECT ON finance.v_account_groups,finance.finance_account_group_events FROM core_finance_ingest;
REVOKE INSERT ON finance.finance_review_events FROM core_finance_ingest;
DROP TRIGGER protect_local_classification ON finance.finance_review_events;
DROP FUNCTION finance.protect_local_classification();
DROP TABLE finance.finance_categorization_results;
DROP TABLE finance.finance_categorization_targets;
ALTER TABLE finance.finance_ingest_jobs DROP CONSTRAINT finance_ingest_jobs_job_kind_check;
ALTER TABLE finance.finance_ingest_jobs ADD CONSTRAINT finance_ingest_jobs_job_kind_check CHECK(job_kind IN ('import','balances','references'));
COMMIT;

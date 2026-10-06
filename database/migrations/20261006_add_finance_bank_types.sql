-- Derived, append-only evidence; the original ledger and owner reviews remain intact.
BEGIN;
SET LOCAL lock_timeout='2s';
CREATE TABLE finance.finance_record_bank_types (
 record_id uuid NOT NULL REFERENCES finance.finance_import_records(id),
 version text NOT NULL CHECK(version='bank-type-v1'),
 transaction_type text NOT NULL REFERENCES finance.finance_transaction_types(code),
 reason_code text NOT NULL CHECK(reason_code IN ('insufficient_bank_evidence','bank_return','card_payment','card_refund','direct_debit','interest_paid','interest_received','bank_fee','fee_refund','bank_reversal','aggregate_entry','conflicting_bank_evidence','source_unavailable')),
 private_data text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(record_id,version)
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_record_bank_types
 FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_record_bank_types
 FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
GRANT SELECT ON finance.finance_record_bank_types TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_record_bank_types TO core_finance_ingest;
CREATE OR REPLACE VIEW finance.v_transactions AS
 SELECT t.*,review.category_code,review.id AS review_id,
 CASE WHEN review.id IS NOT NULL THEN coalesce(review.transaction_type,'UNKNOWN') ELSE coalesce(bank.transaction_type,'UNKNOWN') END AS transaction_type,review.subcategory_code,review.merchant_id,
 coalesce(review.classification_source,CASE WHEN review.id IS NOT NULL THEN CASE WHEN review.source_review_id IS NULL THEN 'MANUAL' ELSE 'MERCHANT' END WHEN bank.transaction_type IS NOT NULL THEN 'RULE' END) AS classification_source,
 review.confidence,coalesce(review.confirmed,review.id IS NOT NULL) AS confirmed,
 review.created_at AS classified_at,coalesce(review.suggestion_method,CASE WHEN review.id IS NULL AND bank.transaction_type IS NOT NULL THEN 'bank-type-v1:'||bank.reason_code END) AS rule_version,review.model_version,
 review.source_review_id AS rule_review_id,review.transfer_id,review.linked_transaction_id,
 coalesce(review.transfer_status,'UNMATCHED') AS transfer_status,merchant.private_data AS merchant_data,
 (review.id IS NOT NULL AND review.transaction_type IS NULL) AS legacy_classification
 FROM finance.finance_transactions t
 LEFT JOIN LATERAL (SELECT * FROM finance.finance_review_events WHERE transaction_id=t.id
   AND (coalesce(confirmed,true) OR (actor='finance-local' AND model_version LIKE 'finance-local-v1:%'))
   ORDER BY coalesce(confirmed,true) DESC,sequence_no DESC LIMIT 1) review ON true
 LEFT JOIN finance.finance_counterparties merchant ON merchant.id=review.merchant_id
 LEFT JOIN LATERAL (
   SELECT CASE WHEN count(DISTINCT k.transaction_type)=1 THEN min(k.transaction_type) END AS transaction_type,
          min(k.reason_code) AS reason_code
   FROM finance.finance_transaction_sources s
   JOIN finance.finance_import_records r ON r.id=s.record_id
   JOIN finance.v_import_status b ON b.id=r.batch_id
   JOIN finance.finance_record_bank_types k ON k.record_id=r.id AND k.version='bank-type-v1'
   WHERE s.transaction_id=t.id AND b.status IN ('imported','partial') AND k.transaction_type<>'UNKNOWN'
 ) bank ON true
 WHERE EXISTS(SELECT 1 FROM finance.finance_transaction_sources s JOIN finance.finance_import_records r ON r.id=s.record_id
 JOIN finance.v_import_status b ON b.id=r.batch_id WHERE s.transaction_id=t.id AND b.status IN ('imported','partial'));
COMMIT;

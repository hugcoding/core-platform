-- Locally classified categories remain below owner-confirmed reviews.
BEGIN;
SET LOCAL lock_timeout='2s';
ALTER TABLE finance.finance_ingest_jobs DROP CONSTRAINT finance_ingest_jobs_job_kind_check;
ALTER TABLE finance.finance_ingest_jobs ADD CONSTRAINT finance_ingest_jobs_job_kind_check CHECK(job_kind IN ('import','balances','references','categorize'));
CREATE TABLE finance.finance_categorization_targets (
 job_id uuid NOT NULL REFERENCES finance.finance_ingest_jobs(id),
 transaction_id uuid NOT NULL REFERENCES finance.finance_transactions(id),
 PRIMARY KEY(job_id,transaction_id)
);
CREATE TABLE finance.finance_categorization_results (
 job_id uuid NOT NULL,transaction_id uuid NOT NULL,
 status text NOT NULL CHECK(status IN ('classified','abstained','skipped')),
 review_id uuid REFERENCES finance.finance_review_events(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(job_id,transaction_id),
 FOREIGN KEY(job_id,transaction_id) REFERENCES finance.finance_categorization_targets(job_id,transaction_id),
 CHECK ((status='classified')=(review_id IS NOT NULL))
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['finance_categorization_targets','finance_categorization_results'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.%I FOR EACH ROW EXECUTE FUNCTION finance.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.%I FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION finance.protect_local_classification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
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
CREATE TRIGGER protect_local_classification BEFORE INSERT ON finance.finance_review_events
 FOR EACH ROW EXECUTE FUNCTION finance.protect_local_classification();
REVOKE ALL ON FUNCTION finance.protect_local_classification() FROM PUBLIC;
GRANT SELECT ON finance.finance_categorization_targets,finance.finance_categorization_results TO core_finance_api,core_finance_ingest;
GRANT SELECT ON finance.v_account_groups,finance.finance_account_group_events TO core_finance_ingest;
GRANT INSERT ON finance.finance_categorization_targets TO core_finance_api;
GRANT INSERT ON finance.finance_categorization_results,finance.finance_review_events TO core_finance_ingest;
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
   AND (coalesce(confirmed,true) OR (actor='finance-local' AND model_version LIKE 'finance-local-v1:%'))
   ORDER BY coalesce(confirmed,true) DESC,sequence_no DESC LIMIT 1) review ON true
 LEFT JOIN finance.finance_counterparties merchant ON merchant.id=review.merchant_id
 WHERE EXISTS(SELECT 1 FROM finance.finance_transaction_sources s JOIN finance.finance_import_records r ON r.id=s.record_id
 JOIN finance.v_import_status b ON b.id=r.batch_id WHERE s.transaction_id=t.id AND b.status IN ('imported','partial'));
COMMIT;

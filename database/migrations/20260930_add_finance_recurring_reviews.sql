BEGIN;
SET LOCAL lock_timeout='2s';
CREATE TABLE finance.finance_recurring_reviews (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 pattern_id uuid NOT NULL REFERENCES finance.finance_recurring_patterns(id),
 detection_id uuid NOT NULL REFERENCES finance.finance_recurring_detections(id),
 status text NOT NULL CHECK(status IN ('confirmed','rejected','inactive','proposed')),
 recurring_type text NOT NULL CHECK(recurring_type IN ('subscription','fixed_cost','periodic_transfer','other_recurring')),
 previous uuid UNIQUE REFERENCES finance.finance_recurring_reviews(id),
 actor text NOT NULL DEFAULT 'owner' CHECK(actor='owner'),
 idempotency_key uuid NOT NULL UNIQUE,
 payload_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX finance_recurring_first_review ON finance.finance_recurring_reviews(pattern_id) WHERE previous IS NULL;
CREATE INDEX finance_recurring_review_latest ON finance.finance_recurring_reviews(pattern_id,sequence_no DESC);
CREATE FUNCTION finance.validate_recurring_review() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM finance.finance_recurring_detections WHERE id=NEW.detection_id AND pattern_id=NEW.pattern_id)
 OR (NEW.previous IS NOT NULL AND NOT EXISTS(SELECT 1 FROM finance.finance_recurring_reviews WHERE id=NEW.previous AND pattern_id=NEW.pattern_id)) THEN
 RAISE EXCEPTION 'finance_recurring_review_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_recurring_review BEFORE INSERT ON finance.finance_recurring_reviews FOR EACH ROW EXECUTE FUNCTION finance.validate_recurring_review();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_recurring_reviews FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_recurring_reviews FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
REVOKE ALL ON FUNCTION finance.validate_recurring_review() FROM PUBLIC;
GRANT SELECT ON finance.finance_recurring_reviews TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_recurring_reviews TO core_finance_api;
GRANT USAGE ON SEQUENCE finance.finance_recurring_reviews_sequence_no_seq TO core_finance_api;
COMMIT;

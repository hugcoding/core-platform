BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE finance.finance_review_events
 ADD COLUMN source_review_id uuid REFERENCES finance.finance_review_events(id),
 ADD COLUMN suggestion_method text,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
   (source_review_id IS NULL AND suggestion_method IS NULL) OR
   (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL
    AND suggestion_method='local-merchant-v1'));
CREATE FUNCTION finance.validate_suggestion_evidence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.source_review_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM finance.finance_review_events s WHERE s.id=NEW.source_review_id
  AND s.source_review_id IS NULL AND s.transaction_id<>NEW.transaction_id
  AND s.category_code=NEW.category_code
 ) THEN RAISE EXCEPTION 'finance_suggestion_evidence_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_suggestion_evidence BEFORE INSERT ON finance.finance_review_events
 FOR EACH ROW EXECUTE FUNCTION finance.validate_suggestion_evidence();
REVOKE ALL ON FUNCTION finance.validate_suggestion_evidence() FROM PUBLIC;
COMMIT;

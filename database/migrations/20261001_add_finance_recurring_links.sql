BEGIN;
SET LOCAL lock_timeout='2s';
CREATE TABLE finance.finance_recurring_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 pattern_id uuid NOT NULL REFERENCES finance.finance_recurring_patterns(id),
 parent_id uuid REFERENCES finance.finance_recurring_patterns(id),
 previous uuid UNIQUE REFERENCES finance.finance_recurring_links(id),
 actor text NOT NULL DEFAULT 'owner' CHECK(actor='owner'),
 idempotency_key uuid NOT NULL UNIQUE, payload_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(pattern_id IS DISTINCT FROM parent_id)
);
CREATE UNIQUE INDEX finance_recurring_link_first ON finance.finance_recurring_links(pattern_id) WHERE previous IS NULL;
CREATE INDEX finance_recurring_link_latest ON finance.finance_recurring_links(pattern_id,sequence_no DESC);
CREATE VIEW finance.v_recurring_membership AS
 SELECT p.id AS pattern_id,coalesce(l.parent_id,p.id) AS root_id,l.id AS link_id
 FROM finance.finance_recurring_patterns p LEFT JOIN LATERAL
 (SELECT id,parent_id FROM finance.finance_recurring_links WHERE pattern_id=p.id ORDER BY sequence_no DESC LIMIT 1) l ON true;
CREATE FUNCTION finance.validate_recurring_link() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('finance-recurring-link'));
 IF NEW.previous IS DISTINCT FROM (SELECT link_id FROM finance.v_recurring_membership WHERE pattern_id=NEW.pattern_id)
 OR (NEW.parent_id IS NOT NULL AND (
  NOT EXISTS(SELECT 1 FROM finance.finance_recurring_patterns a JOIN finance.finance_recurring_patterns b
    ON a.account_id=b.account_id AND a.direction=b.direction AND a.currency=b.currency
    WHERE a.id=NEW.pattern_id AND b.id=NEW.parent_id)
  OR NOT EXISTS(SELECT 1 FROM finance.v_recurring_membership WHERE pattern_id=NEW.parent_id AND root_id=pattern_id)
  OR EXISTS(SELECT 1 FROM finance.v_recurring_membership WHERE root_id=NEW.pattern_id AND pattern_id<>NEW.pattern_id))) THEN
 RAISE EXCEPTION 'finance_recurring_link_mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_recurring_link BEFORE INSERT ON finance.finance_recurring_links FOR EACH ROW EXECUTE FUNCTION finance.validate_recurring_link();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_recurring_links FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_recurring_links FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
REVOKE ALL ON FUNCTION finance.validate_recurring_link() FROM PUBLIC;
GRANT SELECT ON finance.finance_recurring_links,finance.v_recurring_membership TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_recurring_links TO core_finance_api;
GRANT USAGE ON SEQUENCE finance.finance_recurring_links_sequence_no_seq TO core_finance_api;
COMMIT;

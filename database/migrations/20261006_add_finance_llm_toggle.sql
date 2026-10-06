BEGIN;
SET LOCAL lock_timeout='2s';
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_suggestion_evidence,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
 (source_review_id IS NULL AND suggestion_method IS NULL) OR
 (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL AND suggestion_method IN ('local-merchant-v1','local-merchant-v2','local-merchant-v3')));
CREATE TABLE finance.finance_classification_settings_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 llm_enabled boolean NOT NULL,
 actor text NOT NULL DEFAULT 'owner',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_classification_settings_events
 FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_classification_settings_events
 FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
CREATE VIEW finance.v_classification_settings AS
 SELECT coalesce((SELECT llm_enabled FROM finance.finance_classification_settings_events ORDER BY id DESC LIMIT 1),true) AS llm_enabled;
GRANT SELECT ON finance.finance_classification_settings_events,finance.v_classification_settings TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_classification_settings_events TO core_finance_api;
GRANT USAGE ON SEQUENCE finance.finance_classification_settings_events_id_seq TO core_finance_api;
COMMIT;

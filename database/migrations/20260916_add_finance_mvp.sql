-- SCRUM-118. Additive, single-owner MVP; no source or existing event mutation.
BEGIN;
SET LOCAL lock_timeout = '2s';
CREATE SCHEMA finance;
REVOKE ALL ON SCHEMA finance FROM PUBLIC;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='core_finance_api') THEN CREATE ROLE core_finance_api NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='core_finance_ingest') THEN CREATE ROLE core_finance_ingest NOLOGIN; END IF;
END $$;
CREATE TABLE finance.finance_accounts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), identity_key text NOT NULL UNIQUE,
 private_data text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_source_documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), file_id integer NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
 content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'), size_bytes bigint NOT NULL CHECK(size_bytes>0),
 original_ciphertext text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(content_sha256,size_bytes)
);
CREATE TABLE finance.finance_source_occurrences (
 source_id uuid NOT NULL REFERENCES finance.finance_source_documents(id),
 file_id integer NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(source_id,file_id)
);
CREATE TABLE finance.finance_import_batches (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id uuid NOT NULL REFERENCES finance.finance_source_documents(id),
 parser_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_id,parser_version)
);
CREATE TABLE finance.finance_import_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 batch_id uuid NOT NULL REFERENCES finance.finance_import_batches(id),
 status text NOT NULL CHECK(status IN ('received','validated','imported','partial','rejected','rolled_back')),
 reason_code text NOT NULL DEFAULT '', records integer NOT NULL DEFAULT 0 CHECK(records>=0),
 unresolved integer NOT NULL DEFAULT 0 CHECK(unresolved>=0), actor text NOT NULL DEFAULT 'finance-worker',
 idempotency_key text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_import_records (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), batch_id uuid NOT NULL REFERENCES finance.finance_import_batches(id),
 locator text NOT NULL, account_id uuid NOT NULL REFERENCES finance.finance_accounts(id),
 fingerprint text NOT NULL, private_data text NOT NULL, initial_outcome text NOT NULL CHECK(initial_outcome IN ('new','unresolved')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(batch_id,locator)
);
CREATE INDEX finance_record_fingerprint ON finance.finance_import_records(account_id,fingerprint);
CREATE TABLE finance.finance_transactions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_id uuid NOT NULL UNIQUE REFERENCES finance.finance_import_records(id),
 account_id uuid NOT NULL REFERENCES finance.finance_accounts(id), booking_date date NOT NULL,
 value_date date, amount numeric(24,2) NOT NULL CHECK(amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 currency text NOT NULL CHECK(currency='EUR'), fingerprint text NOT NULL,
 private_data text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finance_transactions_account_date ON finance.finance_transactions(account_id,booking_date DESC,id);
CREATE INDEX finance_transactions_fingerprint ON finance.finance_transactions(account_id,fingerprint);
CREATE TABLE finance.finance_transaction_sources (
 record_id uuid PRIMARY KEY REFERENCES finance.finance_import_records(id),
 transaction_id uuid NOT NULL REFERENCES finance.finance_transactions(id), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_categories (code text PRIMARY KEY, label text NOT NULL);
INSERT INTO finance.finance_categories VALUES ('wonen','Wonen'),('boodschappen','Boodschappen'),('vervoer','Vervoer'),
 ('verzekeringen','Verzekeringen'),('abonnementen','Abonnementen'),('vrije_tijd','Vrije tijd'),
 ('inkomen','Inkomen'),('overboekingen','Overboekingen'),('overig','Overig');
CREATE TABLE finance.finance_counterparties (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), identity_key text NOT NULL UNIQUE, private_data text NOT NULL
);
CREATE TABLE finance.finance_review_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sequence_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 transaction_id uuid NOT NULL REFERENCES finance.finance_transactions(id),
 category_code text REFERENCES finance.finance_categories(code),
 supersedes_event_id uuid UNIQUE REFERENCES finance.finance_review_events(id),
 actor text NOT NULL, idempotency_key uuid NOT NULL UNIQUE, payload_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE finance.finance_duplicate_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), record_id uuid NOT NULL UNIQUE REFERENCES finance.finance_import_records(id),
 transaction_id uuid NOT NULL REFERENCES finance.finance_transactions(id), decision text NOT NULL CHECK(decision IN ('same','distinct')),
 actor text NOT NULL, idempotency_key uuid NOT NULL UNIQUE, payload_digest text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX finance_review_first ON finance.finance_review_events(transaction_id) WHERE supersedes_event_id IS NULL;
CREATE TABLE finance.finance_ingest_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), requested_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed')),
 waiting_reason text, attempts integer NOT NULL DEFAULT 0, finished_at timestamptz, error_code text,
 requested_by text NOT NULL DEFAULT 'owner'
);
CREATE UNIQUE INDEX finance_one_open_job ON finance.finance_ingest_jobs((true)) WHERE status IN ('pending','running');
CREATE FUNCTION finance.immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'finance_append_only'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['finance_accounts','finance_source_documents','finance_source_occurrences','finance_import_batches',
 'finance_import_events','finance_import_records','finance_transactions','finance_transaction_sources','finance_categories',
 'finance_counterparties','finance_review_events','finance_duplicate_events'] LOOP
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.%I FOR EACH ROW EXECUTE FUNCTION finance.immutable()',t);
 EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.%I FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION finance.validate_links() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_TABLE_NAME='finance_transactions' THEN
  IF NOT EXISTS(SELECT 1 FROM finance.finance_import_records r WHERE r.id=NEW.record_id AND r.account_id=NEW.account_id)
   OR NOT EXISTS(SELECT 1 FROM finance.finance_transaction_sources s WHERE s.record_id=NEW.record_id AND s.transaction_id=NEW.id) THEN
    RAISE EXCEPTION 'finance_source_link_required'; END IF;
 ELSIF TG_TABLE_NAME='finance_transaction_sources' THEN
  IF NOT EXISTS(SELECT 1 FROM finance.finance_transactions t JOIN finance.finance_import_records r ON r.id=NEW.record_id
     WHERE t.id=NEW.transaction_id AND t.account_id=r.account_id AND t.fingerprint=r.fingerprint) THEN
    RAISE EXCEPTION 'finance_source_link_mismatch'; END IF;
 ELSIF NEW.supersedes_event_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM finance.finance_review_events e WHERE e.id=NEW.supersedes_event_id AND e.transaction_id=NEW.transaction_id) THEN
  RAISE EXCEPTION 'finance_review_predecessor_mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER validate_transaction AFTER INSERT ON finance.finance_transactions DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION finance.validate_links();
CREATE CONSTRAINT TRIGGER validate_source AFTER INSERT ON finance.finance_transaction_sources DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION finance.validate_links();
CREATE TRIGGER validate_review BEFORE INSERT ON finance.finance_review_events FOR EACH ROW EXECUTE FUNCTION finance.validate_links();
CREATE VIEW finance.v_import_status AS
 SELECT b.*, e.status,e.reason_code,e.records,e.unresolved,e.created_at AS status_at FROM finance.finance_import_batches b
 JOIN LATERAL (SELECT * FROM finance.finance_import_events WHERE batch_id=b.id ORDER BY id DESC LIMIT 1) e ON true;
CREATE VIEW finance.v_transactions AS
 SELECT t.*, review.category_code,review.id AS review_id FROM finance.finance_transactions t
 LEFT JOIN LATERAL (SELECT id,category_code FROM finance.finance_review_events WHERE transaction_id=t.id ORDER BY sequence_no DESC LIMIT 1) review ON true
 WHERE EXISTS(SELECT 1 FROM finance.finance_transaction_sources s JOIN finance.finance_import_records r ON r.id=s.record_id
 JOIN finance.v_import_status b ON b.id=r.batch_id WHERE s.transaction_id=t.id AND b.status IN ('imported','partial'));
GRANT USAGE ON SCHEMA finance TO core_finance_api,core_finance_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA finance TO core_finance_api,core_finance_ingest;
GRANT INSERT ON ALL TABLES IN SCHEMA finance TO core_finance_ingest;
GRANT INSERT ON finance.finance_review_events,finance.finance_duplicate_events,finance.finance_transactions,
 finance.finance_transaction_sources,finance.finance_import_events,finance.finance_ingest_jobs TO core_finance_api;
GRANT UPDATE ON finance.finance_ingest_jobs TO core_finance_ingest;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA finance TO core_finance_api,core_finance_ingest;
GRANT SELECT ON public.files TO core_finance_api,core_finance_ingest;
GRANT SELECT,INSERT ON public.folders,public.files TO core_finance_ingest;
GRANT USAGE ON SEQUENCE public.files_id_seq,public.folders_id_seq TO core_finance_ingest;
CREATE FUNCTION finance.runtime_pressure() RETURNS TABLE(busy boolean,sessions bigint)
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM public.v_controlled_execution_batch_progress
 WHERE batch_status IN ('approved','queued','started','rollback_pending')),
 (SELECT count(*) FROM pg_catalog.pg_stat_activity
 WHERE datname=current_database() AND state='active' AND pid<>pg_backend_pid());
$$;
REVOKE ALL ON FUNCTION finance.runtime_pressure() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finance.runtime_pressure() TO core_finance_ingest;
COMMIT;

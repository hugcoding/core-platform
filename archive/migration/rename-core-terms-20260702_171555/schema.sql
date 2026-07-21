--
-- PostgreSQL database dump
--

\restrict KM5I8YsUK7CLbO0daSZ9hUdbrsZeFBT9FWSYUKVNueqkKGoLNR6hGNMoNadS5g0

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg12+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: cleanup_all_execute(); Type: PROCEDURE; Schema: public; Owner: hugo
--

CREATE PROCEDURE public.cleanup_all_execute()
    LANGUAGE plpgsql
    AS $_$
DECLARE
    dir_folders INT := 0;
    dir_files INT := 0;
    dir_meta INT := 0;
    dir_emb INT := 0;
    dir_ai INT := 0;

    file_files INT := 0;
    file_meta INT := 0;
    file_emb INT := 0;
    file_ai INT := 0;

    orphan_metadata INT := 0;
    orphan_embeddings INT := 0;
    orphan_ai INT := 0;
    orphan_files INT := 0;
    orphan_folders INT := 0;
BEGIN
    RAISE NOTICE '=== CLEANUP START ===';

    --------------------------------------------------------------------
    -- 1. SYSTEM FOLDERS (@eaDir, @tmp, @appstore, @*)
    --------------------------------------------------------------------
    WITH excluded_folders AS (
        SELECT id FROM folders
        WHERE path LIKE '%/@eaDir%'
           OR path LIKE '%/@appstore%'
           OR path LIKE '%/@tmp%'
           OR path LIKE '%/@%'
    ),
    files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (SELECT id FROM excluded_folders)
    )
    SELECT
        (SELECT COUNT(*) FROM excluded_folders),
        (SELECT COUNT(*) FROM files_to_delete),
        (SELECT COUNT(*) FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete)),
        (SELECT COUNT(*) FROM embeddings WHERE file_id IN (SELECT file_id FROM files_to_delete)),
        (SELECT COUNT(*) FROM ai_output WHERE file_id IN (SELECT file_id FROM files_to_delete))
    INTO dir_folders, dir_files, dir_meta, dir_emb, dir_ai;

    RAISE NOTICE 'DIRS → removing % folders, % files, % metadata, % embeddings, % ai_output',
        dir_folders, dir_files, dir_meta, dir_emb, dir_ai;

    -- DELETE using fresh CTE
    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM metadata WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM embeddings WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM ai_output WHERE file_id IN (SELECT file_id FROM files_to_delete);

    WITH files_to_delete AS (
        SELECT id AS file_id FROM files
        WHERE folder_id IN (
            SELECT id FROM folders
            WHERE path LIKE '%/@eaDir%'
               OR path LIKE '%/@appstore%'
               OR path LIKE '%/@tmp%'
               OR path LIKE '%/@%'
        )
    )
    DELETE FROM files WHERE id IN (SELECT file_id FROM files_to_delete);

    DELETE FROM folders
    WHERE path LIKE '%/@eaDir%'
       OR path LIKE '%/@appstore%'
       OR path LIKE '%/@tmp%'
       OR path LIKE '%/@%';

    --------------------------------------------------------------------
    -- 2. SYSTEM FILES (~$, ._, .DS_Store, Thumbs.db, *.tmp, *.swp, *.bak)
    --------------------------------------------------------------------
    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    SELECT
        (SELECT COUNT(*) FROM excluded_files),
        (SELECT COUNT(*) FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files)),
        (SELECT COUNT(*) FROM embeddings WHERE file_id IN (SELECT file_id FROM excluded_files)),
        (SELECT COUNT(*) FROM ai_output WHERE file_id IN (SELECT file_id FROM excluded_files))
    INTO file_files, file_meta, file_emb, file_ai;

    RAISE NOTICE 'FILES → removing % files, % metadata, % embeddings, % ai_output',
        file_files, file_meta, file_emb, file_ai;

    -- DELETE using fresh CTE
    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM metadata WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM embeddings WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM ai_output WHERE file_id IN (SELECT file_id FROM excluded_files);

    WITH excluded_files AS (
        SELECT id AS file_id FROM files
        WHERE filename LIKE '~$%'
           OR filename LIKE '._%'
           OR filename = '.DS_Store'
           OR filename = 'Thumbs.db'
           OR filename LIKE '%.tmp'
           OR filename LIKE '%.swp'
           OR filename LIKE '%.bak'
    )
    DELETE FROM files WHERE id IN (SELECT file_id FROM excluded_files);

    --------------------------------------------------------------------
    -- 3. ORPHANS (metadata, embeddings, ai_output, files, folders)
    --------------------------------------------------------------------
    SELECT COUNT(*) INTO orphan_metadata
    FROM metadata m LEFT JOIN files f ON f.id = m.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned metadata', orphan_metadata;

    DELETE FROM metadata m
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = m.file_id);

    SELECT COUNT(*) INTO orphan_embeddings
    FROM embeddings e LEFT JOIN files f ON f.id = e.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned embeddings', orphan_embeddings;

    DELETE FROM embeddings e
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = e.file_id);

    SELECT COUNT(*) INTO orphan_ai
    FROM ai_output a LEFT JOIN files f ON f.id = a.file_id
    WHERE f.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned ai_output', orphan_ai;

    DELETE FROM ai_output a
    WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = a.file_id);

    SELECT COUNT(*) INTO orphan_files
    FROM files fl LEFT JOIN folders fo ON fo.id = fl.folder_id
    WHERE fo.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned files', orphan_files;

    DELETE FROM files fl
    WHERE NOT EXISTS (SELECT 1 FROM folders fo WHERE fo.id = fl.folder_id);

    SELECT COUNT(*) INTO orphan_folders
    FROM folders f LEFT JOIN folders p ON p.id = f.parent_id
    WHERE f.parent_id IS NOT NULL AND p.id IS NULL;

    RAISE NOTICE 'ORPHANS → removing % orphaned folders', orphan_folders;

    DELETE FROM folders f
    WHERE f.parent_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM folders p WHERE p.id = f.parent_id);

    --------------------------------------------------------------------
    RAISE NOTICE '=== CLEANUP COMPLETE ===';
END;
$_$;


ALTER PROCEDURE public.cleanup_all_execute() OWNER TO hugo;

--
-- Name: create_scan_session(text); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.create_scan_session(scan_type text) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    sid UUID := gen_random_uuid();
BEGIN
    INSERT INTO scan_sessions(id, type)
    VALUES (sid, scan_type);
    RETURN sid;
END;
$$;


ALTER FUNCTION public.create_scan_session(scan_type text) OWNER TO hugo;

--
-- Name: finish_scan_session(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.finish_scan_session(sid uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET finished_at = NOW(),
        status = 'done'
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.finish_scan_session(sid uuid) OWNER TO hugo;

--
-- Name: increment_files_discovered(uuid, integer); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_files_discovered(sid uuid, cnt integer) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET files_discovered = files_discovered + cnt
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_files_discovered(sid uuid, cnt integer) OWNER TO hugo;

--
-- Name: increment_jobs_enqueued(uuid, integer); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_jobs_enqueued(sid uuid, cnt integer) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET jobs_enqueued = jobs_enqueued + cnt
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_jobs_enqueued(sid uuid, cnt integer) OWNER TO hugo;

--
-- Name: increment_jobs_processed(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.increment_jobs_processed(sid uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE scan_sessions
    SET jobs_processed = jobs_processed + 1
    WHERE id = sid;
END;
$$;


ALTER FUNCTION public.increment_jobs_processed(sid uuid) OWNER TO hugo;

--
-- Name: is_scan_complete(uuid); Type: FUNCTION; Schema: public; Owner: hugo
--

CREATE FUNCTION public.is_scan_complete(sid uuid) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE done BOOLEAN;
BEGIN
    SELECT (status='done' AND jobs_enqueued>0 AND jobs_processed>=jobs_enqueued)
    INTO done
    FROM scan_sessions WHERE id=sid;
    RETURN COALESCE(done, FALSE);
END;
$$;


ALTER FUNCTION public.is_scan_complete(sid uuid) OWNER TO hugo;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_output; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.ai_output (
    id integer NOT NULL,
    file_id integer,
    summary text,
    tags text[],
    categories text[],
    embedding public.vector(1536),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.ai_output OWNER TO hugo;

--
-- Name: ai_output_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.ai_output_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ai_output_id_seq OWNER TO hugo;

--
-- Name: ai_output_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.ai_output_id_seq OWNED BY public.ai_output.id;


--
-- Name: embeddings; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.embeddings (
    id integer NOT NULL,
    file_id integer NOT NULL,
    embedding public.vector(1536),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.embeddings OWNER TO hugo;

--
-- Name: embeddings_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.embeddings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.embeddings_id_seq OWNER TO hugo;

--
-- Name: embeddings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.embeddings_id_seq OWNED BY public.embeddings.id;


--
-- Name: files; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.files (
    id integer NOT NULL,
    folder_id integer NOT NULL,
    filename text NOT NULL,
    extension text,
    size_bytes bigint,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    modified_at_fs bigint,
    inode bigint,
    xxhash text,
    path text,
    mime_type text,
    deleted_at timestamp without time zone,
    hash_content text,
    hash_path text,
    source text
);


ALTER TABLE public.files OWNER TO hugo;

--
-- Name: files_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.files_id_seq OWNER TO hugo;

--
-- Name: files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.files_id_seq OWNED BY public.files.id;


--
-- Name: folders; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.folders (
    id integer NOT NULL,
    path text NOT NULL,
    parent_id integer,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.folders OWNER TO hugo;

--
-- Name: folders_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.folders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.folders_id_seq OWNER TO hugo;

--
-- Name: folders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.folders_id_seq OWNED BY public.folders.id;


--
-- Name: metadata; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.metadata (
    id integer NOT NULL,
    file_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    mime_type text,
    width integer,
    height integer,
    duration double precision,
    missing boolean DEFAULT false
);


ALTER TABLE public.metadata OWNER TO hugo;

--
-- Name: metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: hugo
--

CREATE SEQUENCE public.metadata_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.metadata_id_seq OWNER TO hugo;

--
-- Name: metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: hugo
--

ALTER SEQUENCE public.metadata_id_seq OWNED BY public.metadata.id;


--
-- Name: scan_sessions; Type: TABLE; Schema: public; Owner: hugo
--

CREATE TABLE public.scan_sessions (
    id uuid NOT NULL,
    type text NOT NULL,
    started_at timestamp without time zone DEFAULT now() NOT NULL,
    finished_at timestamp without time zone,
    status text DEFAULT 'running'::text NOT NULL,
    files_discovered integer DEFAULT 0 NOT NULL,
    jobs_enqueued integer DEFAULT 0 NOT NULL,
    jobs_processed integer DEFAULT 0 NOT NULL,
    CONSTRAINT scan_sessions_status_check CHECK ((status = ANY (ARRAY['running'::text, 'finished'::text, 'failed'::text, 'aborted'::text]))),
    CONSTRAINT scan_sessions_type_check CHECK ((type = ANY (ARRAY['full'::text, 'interval'::text, 'watcher'::text])))
);


ALTER TABLE public.scan_sessions OWNER TO hugo;

--
-- Name: v_files_last_hour; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_files_last_hour AS
 SELECT count(*) AS files_last_hour
   FROM public.files
  WHERE (updated_at >= ((now() AT TIME ZONE 'UTC'::text) - '01:00:00'::interval));


ALTER VIEW public.v_files_last_hour OWNER TO hugo;

--
-- Name: v_files_over_time_extended; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_files_over_time_extended AS
 WITH per_day AS (
         SELECT date(files.created_at) AS file_date,
            count(*) AS files_created,
            ((count(*))::numeric / 24.0) AS avg_files_per_hour_that_day
           FROM public.files
          GROUP BY (date(files.created_at))
          ORDER BY (date(files.created_at))
        ), global_stats AS (
         SELECT count(*) AS total_files,
            min(files.created_at) AS first_file,
            max(files.created_at) AS last_file,
            (EXTRACT(epoch FROM (max(files.created_at) - min(files.created_at))) / (3600)::numeric) AS hours_span
           FROM public.files
        )
 SELECT p.file_date,
    p.files_created,
    p.avg_files_per_hour_that_day,
    g.total_files,
    g.first_file,
    g.last_file,
    g.hours_span,
        CASE
            WHEN (g.hours_span < (1)::numeric) THEN NULL::numeric
            ELSE ((g.total_files)::numeric / g.hours_span)
        END AS avg_files_per_hour_global
   FROM (per_day p
     CROSS JOIN global_stats g)
  ORDER BY p.file_date;


ALTER VIEW public.v_files_over_time_extended OWNER TO hugo;

--
-- Name: v_scan_status; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_scan_status AS
 SELECT id,
    type,
    status,
    started_at,
    finished_at,
    files_discovered,
    jobs_enqueued,
    jobs_processed,
    round((((jobs_processed)::numeric / (NULLIF(jobs_enqueued, 0))::numeric) * (100)::numeric), 2) AS progress_percent
   FROM public.scan_sessions
  ORDER BY started_at DESC;


ALTER VIEW public.v_scan_status OWNER TO hugo;

--
-- Name: v_test_documents; Type: VIEW; Schema: public; Owner: hugo
--

CREATE VIEW public.v_test_documents AS
 SELECT f.id,
    f.folder_id,
    f.filename,
    f.extension,
    f.size_bytes,
    f.created_at,
    f.updated_at,
    f.modified_at_fs,
    f.inode,
    f.xxhash,
    fo.path
   FROM (public.files f
     JOIN public.folders fo ON ((fo.id = f.folder_id)))
  WHERE (fo.path ~~ '/volume1/backup/NITRO/D/data/hugo/Documents%'::text);


ALTER VIEW public.v_test_documents OWNER TO hugo;

--
-- Name: ai_output id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output ALTER COLUMN id SET DEFAULT nextval('public.ai_output_id_seq'::regclass);


--
-- Name: embeddings id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings ALTER COLUMN id SET DEFAULT nextval('public.embeddings_id_seq'::regclass);


--
-- Name: files id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files ALTER COLUMN id SET DEFAULT nextval('public.files_id_seq'::regclass);


--
-- Name: folders id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders ALTER COLUMN id SET DEFAULT nextval('public.folders_id_seq'::regclass);


--
-- Name: metadata id; Type: DEFAULT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata ALTER COLUMN id SET DEFAULT nextval('public.metadata_id_seq'::regclass);


--
-- Name: ai_output ai_output_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output
    ADD CONSTRAINT ai_output_pkey PRIMARY KEY (id);


--
-- Name: embeddings embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings
    ADD CONSTRAINT embeddings_pkey PRIMARY KEY (id);


--
-- Name: files files_path_unique; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_path_unique UNIQUE (path);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: folders folders_path_key; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_path_key UNIQUE (path);


--
-- Name: folders folders_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_pkey PRIMARY KEY (id);


--
-- Name: metadata metadata_file_id_unique; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_file_id_unique UNIQUE (file_id);


--
-- Name: metadata metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_pkey PRIMARY KEY (id);


--
-- Name: scan_sessions scan_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.scan_sessions
    ADD CONSTRAINT scan_sessions_pkey PRIMARY KEY (id);


--
-- Name: idx_files_folder_filename; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_folder_filename ON public.files USING btree (folder_id, filename);


--
-- Name: idx_files_inode_mtime; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_inode_mtime ON public.files USING btree (inode, modified_at_fs);


--
-- Name: idx_files_xxhash; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_files_xxhash ON public.files USING btree (xxhash);


--
-- Name: idx_folders_parent_id; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_folders_parent_id ON public.folders USING btree (parent_id);


--
-- Name: idx_metadata_file_id; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_file_id ON public.metadata USING btree (file_id);


--
-- Name: idx_metadata_mime_type; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_mime_type ON public.metadata USING btree (mime_type);


--
-- Name: idx_metadata_width_height; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_metadata_width_height ON public.metadata USING btree (width, height);


--
-- Name: idx_scan_sessions_started_at; Type: INDEX; Schema: public; Owner: hugo
--

CREATE INDEX idx_scan_sessions_started_at ON public.scan_sessions USING btree (started_at DESC);


--
-- Name: ai_output ai_output_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.ai_output
    ADD CONSTRAINT ai_output_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: embeddings embeddings_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.embeddings
    ADD CONSTRAINT embeddings_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: files files_folder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES public.folders(id) ON DELETE CASCADE;


--
-- Name: folders folders_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.folders(id) ON DELETE CASCADE;


--
-- Name: metadata metadata_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hugo
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict KM5I8YsUK7CLbO0daSZ9hUdbrsZeFBT9FWSYUKVNueqkKGoLNR6hGNMoNadS5g0


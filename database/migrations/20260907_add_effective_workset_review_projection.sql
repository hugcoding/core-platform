-- One read-only projection for the effective Workset filters used by the portal and SQL clients.
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE OR REPLACE FUNCTION public.core_workset_family(
    filename text,
    source_path text,
    accepted_family text DEFAULT NULL
) RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $function$
    WITH evidence AS (
        SELECT ' ' || lower(replace(concat_ws(' ', filename, source_path, accepted_family), '-', ' ')) || ' ' AS value,
               regexp_split_to_array(lower(regexp_replace(coalesce(filename, ''), '\.[^.]*$', '')), '[^a-z0-9]+') AS tokens
    )
    SELECT CASE
        WHEN nullif(lower(trim(accepted_family)), '') IS NOT NULL THEN lower(trim(accepted_family))
        WHEN 'cv' = ANY(tokens) OR value LIKE '%curriculum vitae%' THEN 'resumes'
        WHEN value LIKE ANY (ARRAY['%vacature%', '%functieprofiel%']) THEN 'vacancies'
        WHEN value LIKE ANY (ARRAY['%motivatie%', '%sollicitatiebrief%']) THEN 'motivation_letters'
        WHEN value LIKE ANY (ARRAY['%gesprek%', '%voorbereiding%', '%pitch%']) THEN 'interview_preparation'
        WHEN value LIKE ANY (ARRAY['%arbeidscontract%', '%arbeidsovereenkomst%', '%arbeidsvoorwaarden%', '%werkgeversverklaring%', '%werkgever%', '%dienstverband%']) THEN 'employment_documents'
        WHEN value LIKE ANY (ARRAY['%salarisstrook%', '%salarisspecificatie%', '%loonstrook%', '%loonspecificatie%', '%salary slip%', '%payslip%', '%pay slip%', '%payroll%']) THEN 'salary_slips'
        WHEN value LIKE ANY (ARRAY['%jaaropgave%', '%jaaropgaaf%', '%jaarstaat%', '%annual statement%']) THEN 'annual_income_statements'
        WHEN value LIKE ANY (ARRAY['%declaratie%', '%expense%', '%onkosten%', '%reiskosten%', '%parking%']) THEN 'expense_claims'
        WHEN value LIKE ANY (ARRAY['%uitkering%', '%uitkeringsspecificatie%', '% uwv %', '%werkloosheidswet%']) THEN 'benefit_documents'
        WHEN value LIKE ANY (ARRAY['%pensioen%', '%pensioenoverzicht%', '%uniform pensioenoverzicht%', '%pensioenfonds%']) OR 'upo' = ANY(tokens) THEN 'pension_documents'
        WHEN value LIKE ANY (ARRAY['%getuigschrift%', '%referentie%', '%aanbeveling%', '%reference letter%', '%recommendation%']) THEN 'references_testimonials'
        WHEN value LIKE ANY (ARRAY['%functioneringsgesprek%', '%beoordelingsgesprek%', '%functioneringsverslag%', '%beoordeling%', '%performance review%']) THEN 'performance_reviews'
        WHEN value LIKE ANY (ARRAY['%vereniging van eigenaars%', '%riolering%']) OR 'vve' = ANY(tokens) THEN 'vve_documents'
        WHEN value LIKE ANY (ARRAY['%onderhoud%', '%reparatie%', '%verbouwing%']) THEN 'home_maintenance'
        WHEN value LIKE ANY (ARRAY['%huurcontract%', '%huurovereenkomst%', '%koopakte%', '%koopcontract%', '%koopovereenkomst%', '%woning%']) THEN 'housing_contracts'
        WHEN value LIKE ANY (ARRAY['%eigendomsakte%', '%leveringsakte%', '%kadaster%', '%kadastraal%', '%splitsingsakte%', '%eigendom%']) THEN 'property_documents'
        WHEN value LIKE ANY (ARRAY['%hypotheek%', '%hypotheekakte%', '%hypotheekofferte%', '%renteoverzicht%', '%jaaropgave hypotheek%']) THEN 'mortgage_documents'
        WHEN value LIKE ANY (ARRAY['%woz%', '%ozb%', '%gemeentelijke belastingen%', '%afvalstoffenheffing%', '%rioolheffing%']) THEN 'municipal_housing_documents'
        WHEN value LIKE ANY (ARRAY['%bouwtekening%', '%plattegrond%', '%energielabel%', '%inspectierapport%', '%bouwkundig rapport%', '%meetrapport%']) THEN 'technical_home_documents'
        WHEN value LIKE ANY (ARRAY['%energie%', '%water%', '%gas%', '%elektriciteit%', '%internet%', '%provider%']) THEN 'utilities'
        WHEN value LIKE ANY (ARRAY['%belasting%', '%belastingdienst%', '%aangifte%', '%aanslag%', '%toeslag%']) THEN 'tax_documents'
        WHEN value LIKE ANY (ARRAY['%factuur%', '%nota%', '%invoice%']) THEN 'invoices'
        WHEN value LIKE ANY (ARRAY['%bank%', '%rekening%', '%afschrift%']) THEN 'bank_documents'
        WHEN value LIKE ANY (ARRAY['%verzekering%', '%verzekeraar%', '%polis%', '%premie%', '%schade%', '%dekking%']) THEN 'insurance_documents'
        WHEN value LIKE ANY (ARRAY['%lening%', '%krediet%', '%aflossing%']) THEN 'loans_credit'
        WHEN value LIKE ANY (ARRAY['%spaarrekening%', '%belegging%', '%portfolio%', '%effecten%', '%broker%']) THEN 'savings_investments'
        WHEN value LIKE ANY (ARRAY['%garantie%', '%aankoopbewijs%', '%kassabon%', '%receipt%']) THEN 'warranties_receipts'
        WHEN value LIKE ANY (ARRAY['%abonnement%', '%subscription%', '%lidmaatschap%', '%telecom%']) THEN 'subscriptions'
        WHEN value LIKE ANY (ARRAY['%huisarts%', '%ziekenhuis%', '%medisch%', '%zorg%']) THEN 'health_documents'
        WHEN value LIKE ANY (ARRAY['%laboratorium%', '%labuitslag%', '%röntgen%', '%diagnostiek%']) THEN 'medical_results'
        WHEN value LIKE ANY (ARRAY['%verwijzing%', '%verwijsbrief%', '%behandelplan%', '%afspraakbevestiging%', '%specialist%']) THEN 'medical_referrals'
        WHEN value LIKE ANY (ARRAY['%gezin%', '%ouder%', '%kind%', '%ouderschap%', '%gezinsplan%', '%familie%']) THEN 'family_documents'
        WHEN value LIKE ANY (ARRAY['%kinderopvang%', '%kinderdagverblijf%', '%bso%', '%gastouder%', '%opvangcontract%']) THEN 'childcare_documents'
        WHEN value LIKE ANY (ARRAY['%school%', '%ouderavond%', '%schooljaar%', '%leerling%', '%inschrijving school%']) THEN 'school_documents'
        WHEN value LIKE ANY (ARRAY['%certificaat%', '%certificate%', '%diploma%']) THEN 'certificates'
        WHEN value LIKE ANY (ARRAY['%cursus%', '%opleiding%', '%studie%']) THEN 'course_material'
        WHEN value LIKE ANY (ARRAY['%inschrijfbewijs%', '%opleidingsovereenkomst%', '%studieovereenkomst%', '%collegegeld%', '%student%']) THEN 'education_administration'
        WHEN value LIKE ANY (ARRAY['%paspoort%', '%identiteitskaart%', '%id kaart%', '%rijbewijs%']) THEN 'identity_documents'
        WHEN value LIKE ANY (ARRAY['%geboorteakte%', '%huwelijksakte%', '%uittreksel%', '%basisregistratie%', '%burgerlijke stand%']) OR 'brp' = ANY(tokens) THEN 'personal_records'
        WHEN value LIKE ANY (ARRAY['%booking%', '%boeking%', '%reservering%', '%hotel%', '%vakantiepark%', '%camping%', '%accommodatie%', '%vlucht%', '%trein%']) THEN 'travel_bookings'
        WHEN value LIKE ANY (ARRAY['%ticket%', '%boarding pass%', '%voucher%', '%reisschema%', '%reisbescheiden%']) THEN 'travel_documents'
        WHEN value LIKE ANY (ARRAY['%overeenkomst%', '%contractuele afspraken%', '%akte%']) THEN 'agreements'
        WHEN value LIKE ANY (ARRAY['%beschikking%', '%besluit%', '%kennisgeving%', '%officiële brief%', '%overheidsbrief%']) THEN 'official_correspondence'
        WHEN value LIKE ANY (ARRAY['%gemeente%', '%rijksoverheid%', '%digid%', '%svb%', '%duo%', '%overheid%']) THEN 'government_documents'
        WHEN value LIKE ANY (ARRAY['%bezwaar%', '%beroepschrift%', '%geschil%', '%ingebrekestelling%', '%aansprakelijkstelling%']) THEN 'objections_appeals'
        WHEN value LIKE ANY (ARRAY['%rapport%', '%advies%', '%analyse%']) THEN 'reports_advice'
        WHEN value LIKE ANY (ARRAY['%formulier%', '%aanvraagformulier%', '%bewijsstuk%', '%verklaring%', '%machtiging%']) THEN 'forms_evidence'
        ELSE 'general'
    END
    FROM evidence;
$function$;

CREATE OR REPLACE FUNCTION public.core_normalized_document_identity(filename text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $function$
DECLARE
    stem text := lower(regexp_replace(coalesce(filename, ''), '\.[^.]*$', ''));
BEGIN
    stem := regexp_replace(stem, '\s*[-_ ]\s*(en|nl|engels|nederlands)\s*$', '');
    stem := regexp_replace(stem, '\s*[\[(](kopie|copy)?\s*\d+[\])]\s*$', '');
    stem := regexp_replace(stem, '\s*[-_ ]\s*(kopie|copy)\s*\d*\s*$', '');
    stem := regexp_replace(stem, '[-_ ]+\d{1,2}[.\-_]\d{1,2}[.\-_]\d{2,4}\s*$', '');
    stem := regexp_replace(stem, '[-_ ]+\d{4}[.\-_]\d{1,2}[.\-_]\d{1,2}\s*$', '');
    stem := regexp_replace(stem, '[-_ ]+\d{8}\s*$', '');
    stem := regexp_replace(stem, '[-_ ]+(19|20)\d{2}\s*$', '');
    stem := regexp_replace(stem, '[-_ ]+\d{6,}\s*$', '');
    RETURN trim(regexp_replace(stem, '[^a-z0-9]+', ' ', 'g'));
END;
$function$;

CREATE OR REPLACE VIEW public.v_effective_document_workset AS
WITH latest_target AS (
    SELECT DISTINCT ON (file_id)
        id, file_id, decision, corrected_category_code, corrected_document_family_code,
        created_at
    FROM public.document_review_events
    WHERE review_type = 'target_path'
    ORDER BY file_id, created_at DESC, id DESC
), latest_lifecycle AS (
    SELECT DISTINCT ON (file_id)
        file_id, corrected_lifecycle, lifecycle_active_until, created_at
    FROM public.document_review_events
    WHERE review_type = 'lifecycle'
    ORDER BY file_id, created_at DESC, id DESC
), similarity_redundant AS (
    -- Deliberately avoid the execution-progress projection here: family/status
    -- filtering only needs the selected leader and must stay cheap.
    SELECT
        redundant.file_id,
        review.id AS similarity_review_event_id,
        COALESCE(NULLIF(leader_review.corrected_category_code, ''), leader_class.category)
            AS inherited_category,
        COALESCE(NULLIF(leader_review.corrected_document_family_code, ''), leader_class.document_family)
            AS inherited_document_family
    FROM public.v_latest_pdf_content_similarity_review review
    CROSS JOIN LATERAL unnest(review.redundant_file_ids) redundant(file_id)
    LEFT JOIN public.v_current_file_classification leader_class
      ON leader_class.file_id = review.selected_file_id
    LEFT JOIN public.v_latest_document_review leader_review
      ON leader_review.file_id = review.selected_file_id
     AND leader_review.review_type = 'target_path'
     AND leader_review.decision = 'accepted'
    WHERE review.action = 'selected_leader'
), accepted_identity_counts AS (
    SELECT
        public.core_normalized_document_identity(f.filename) AS identity,
        r.corrected_category_code AS category,
        r.corrected_document_family_code AS family,
        count(*) AS support
    FROM public.v_latest_document_review r
    JOIN public.files f ON f.id = r.file_id
    WHERE r.review_type = 'target_path'
      AND r.decision = 'accepted'
      AND nullif(r.corrected_category_code, '') IS NOT NULL
      AND nullif(r.corrected_document_family_code, '') IS NOT NULL
      AND lower(coalesce(f.extension, '')) IN ('pdf', 'docx', 'xlsx')
      AND length(public.core_normalized_document_identity(f.filename)) >= 5
    GROUP BY 1, 2, 3
), ranked_identity_consensus AS (
    SELECT
        counts.*,
        row_number() OVER (PARTITION BY identity ORDER BY support DESC, category, family) AS position,
        lead(support, 1, 0) OVER (PARTITION BY identity ORDER BY support DESC, category, family) AS second_support
    FROM accepted_identity_counts counts
), identity_consensus AS (
    SELECT identity, category, family
    FROM ranked_identity_consensus
    WHERE position = 1 AND support > second_support
), resolved AS (
    SELECT
        w.*,
        t.id AS latest_target_review_id,
        t.decision AS latest_target_review_decision,
        CASE
            WHEN l.corrected_lifecycle = 'active'
             AND l.lifecycle_active_until IS NOT NULL
             AND l.lifecycle_active_until <= now()
                THEN CASE w.workset_status WHEN 'active' THEN 'active' WHEN 'inactive' THEN 'archive' ELSE 'needs_review' END
            ELSE COALESCE(l.corrected_lifecycle,
                CASE w.workset_status WHEN 'active' THEN 'active' WHEN 'inactive' THEN 'archive' ELSE 'needs_review' END)
        END AS effective_lifecycle,
        COALESCE(
            CASE WHEN t.decision = 'accepted' THEN t.corrected_category_code END,
            c.category
        ) AS effective_category,
        COALESCE(
            CASE WHEN t.decision = 'accepted' THEN t.corrected_document_family_code END,
            c.document_family
        ) AS accepted_family,
        location.location_kind,
        similarity.similarity_review_event_id,
        similarity.inherited_category,
        similarity.inherited_document_family,
        consensus.category AS consensus_category,
        consensus.family AS consensus_family
    FROM public.v_active_document_workset w
    LEFT JOIN latest_target t ON t.file_id = w.file_id
    LEFT JOIN latest_lifecycle l ON l.file_id = w.file_id
    LEFT JOIN public.v_current_file_classification c ON c.file_id = w.file_id
    LEFT JOIN public.v_workset_current_physical_location location ON location.file_id = w.file_id
    LEFT JOIN similarity_redundant similarity ON similarity.file_id = w.file_id
    LEFT JOIN identity_consensus consensus
      ON consensus.identity = public.core_normalized_document_identity(w.filename)
     AND lower(coalesce(w.extension, '')) IN ('pdf', 'docx', 'xlsx')
     AND length(public.core_normalized_document_identity(w.filename)) >= 5
)
SELECT
    r.*,
    CASE
        WHEN r.location_kind = 'deletion_quarantine' OR r.similarity_review_event_id IS NOT NULL THEN 'quarantine'
        WHEN r.effective_lifecycle = 'active' THEN 'active'
        WHEN r.effective_lifecycle = 'archive' THEN 'inactive'
        ELSE 'needs_review'
    END AS effective_workset_status,
    COALESCE(r.inherited_category, r.effective_category, r.consensus_category) AS review_category,
    COALESCE(
        r.inherited_document_family,
        r.accepted_family,
        r.consensus_family,
        public.core_workset_family(r.filename, r.path, r.accepted_family)
    ) AS review_family,
    CASE WHEN r.latest_target_review_id IS NULL THEN 'pending' ELSE 'reviewed' END AS review_state
FROM resolved r;

COMMENT ON VIEW public.v_effective_document_workset IS
    'Read-only effective Workset filter projection: lifecycle overrides, quarantine, latest target review and deterministic family bucket in one SQL source.';

COMMIT;

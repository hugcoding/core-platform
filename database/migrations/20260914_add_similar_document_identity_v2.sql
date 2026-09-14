-- SCRUM-146: conservative cross-format/version identity for review reuse.
-- This only changes a deterministic projection helper; it never mutates files or reviews.
CREATE OR REPLACE FUNCTION public.core_normalized_document_identity(filename text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $function$
DECLARE
    stem text := lower(regexp_replace(coalesce(filename, ''), '\.[^.]*$', ''));
    previous text;
    identity text;
BEGIN
    LOOP
        previous := stem;
        stem := regexp_replace(stem, '^\s*(signed|ondertekend|getekend)[-_ ]+', '');
        stem := regexp_replace(stem, '\s*[-_ ]\s*(signed|ondertekend|getekend)\s*$', '');
        stem := regexp_replace(stem, '\s*[-_ ]\s*(gecomprimeerd|compressed)\s*$', '');
        stem := regexp_replace(stem, '\s*[-_ ]\s*(definitief|final)\s*$', '');
        stem := regexp_replace(stem, '\s*[-_ ]\s*(versie|version|vs?|rev)\s*\d+([._-]\d+)*\s*$', '');
        stem := regexp_replace(stem, '\s*[-_ ]\s*(en|nl|engels|nederlands)\s*$', '');
        stem := regexp_replace(stem, '\s*[\[(](kopie|copy)?\s*\d+[\])]\s*$', '');
        stem := regexp_replace(stem, '\s*[-_ ]\s*(kopie|copy)\s*\d*\s*$', '');
        stem := regexp_replace(stem, '[-_ ]+\d{1,2}[.\-_]\d{1,2}[.\-_]\d{2,4}\s*$', '');
        stem := regexp_replace(stem, '[-_ ]+\d{4}[.\-_]\d{1,2}[.\-_]\d{1,2}\s*$', '');
        stem := regexp_replace(stem, '[-_ ]+\d{8}\s*$', '');
        stem := regexp_replace(stem, '[-_ ]+(19|20)\d{2}\s*$', '');
        stem := regexp_replace(stem, '[-_ ]+\d{6,}\s*$', '');
        EXIT WHEN stem = previous;
    END LOOP;
    identity := trim(regexp_replace(stem, '[^a-z0-9]+', ' ', 'g'));
    IF identity = 'tuin' THEN
        RETURN 'short:tuin';
    END IF;
    IF length(identity) < 5 OR identity = ANY (
        ARRAY['bestand', 'brief', 'document', 'formulier', 'image', 'lijst', 'scan']
    ) THEN
        RETURN '';
    END IF;
    RETURN identity;
END;
$function$;

COMMENT ON FUNCTION public.core_normalized_document_identity(text) IS
    'similar-document-review-v2: conservative identity used only for advisory human-review reuse';

-- Restore the v1 identity helper. The effective workset view depends on this function.
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

COMMENT ON FUNCTION public.core_normalized_document_identity(text) IS
    'similar-document-review-v1: cautious identity used for advisory human-review reuse';

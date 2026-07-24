BEGIN;

UPDATE public.file_events
SET event_status = 'invalidated',
    reviewed_at = now(),
    review_reason =
        'False positive before filesystem_device + inode matching; paths are in different Synology/Btrfs filesystem contexts.'
WHERE id IN (
    'a98a3b90-a7b8-4c68-9051-b55896134957'::uuid,
    'b1939621-c086-4e27-aced-a68fa9326a03'::uuid
)
  AND event_type = 'HARDLINK_DETECTED'
  AND event_status = 'active';

DO $$
DECLARE
    corrected integer;
BEGIN
    SELECT count(*) INTO corrected
    FROM public.file_events
    WHERE id IN (
        'a98a3b90-a7b8-4c68-9051-b55896134957'::uuid,
        'b1939621-c086-4e27-aced-a68fa9326a03'::uuid
    )
      AND event_status = 'invalidated';
    IF corrected <> 2 THEN
        RAISE EXCEPTION 'Expected 2 invalidated events, found %', corrected;
    END IF;
END;
$$;

COMMIT;

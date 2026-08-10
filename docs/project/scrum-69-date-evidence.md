# SCRUM-69 — Generieke datum-evidence en provenance

## Doel

CORE bewaart documentdatums als afzonderlijke bronwaarnemingen. Een datum uit Office,
PDF, toekomstig mediaformaat of filesystem wordt niet stilzwijgend de waarheid en krijgt
geen formaat-specifieke kolom in `metadata`. Providerfase v1 ondersteunt DOCX, XLSX en PDF.

## Datamodel

`file_date_evidence` is append-only en bevat:

- `file_id`, optionele `content_group_id` en de bijbehorende `content_sha256`;
- `evidence_scope`: embedded metadata hoort bij content; latere filesystemevidence bij een file;
- uniforme `date_type`, zoals `created` of `modified`;
- `source_type`, oorspronkelijk `source_field` en ruwe waarde;
- UTC-waarde wanneer de bron een tijdzone bevat;
- lokale klokwaarde en expliciete tijdzonestatus;
- confidence, extractorversie, details en een stabiele `idempotency_key`.

`metadata.created_at` blijft uitsluitend het aanmaakmoment van het CORE-metadatarecord.

### Idempotency key

De `idempotency_key` is een SHA-256-sleutel waarmee CORE vaststelt dat exact dezelfde
bronwaarneming al is verwerkt. Voor datum-evidence bevat de invoer minimaal:

- `evidence_scope`;
- bij content-scope de `content_sha256`, bij file-scope de `file_id`;
- `date_type`, `source_type` en `source_field`;
- de ongewijzigde `raw_value`;
- de `extractor_version`.

De database dwingt uniciteit af. Bij herhaling gebruikt de writer:

```sql
ON CONFLICT (idempotency_key) DO NOTHING
```

Daardoor maakte de tweede ACC-backfill nul nieuwe records. Exacte duplicates delen voor
embedded metadata dezelfde content-sleutel en veroorzaken dus geen dubbele evidence.
Wanneer de contenthash, bronwaarde, bron, datumsoort of extractorversie verandert, ontstaat
bewust een nieuwe key en blijft de eerdere observatie als historie bestaan.

```mermaid
flowchart LR
    F["files + content hash"] --> P["datumprovider"]
    P --> O["Office core properties"]
    P --> D["PDF info dictionary"]
    O --> E["file_date_evidence<br/>append-only"]
    D --> E
    E --> V["v_file_temporal_profile"]
    V --> W["active workset<br/>latere integratie"]
```

## Providers v1

| Formaat | Bron | Velden | Confidence |
|---|---|---|---|
| DOCX/XLSX | OOXML core properties | `dcterms:created`, `dcterms:modified` | medium met tijdzone; low zonder tijdzone |
| PDF | Information Dictionary en XMP | `/CreationDate`, `/ModDate`, `xmp:CreateDate`, `xmp:ModifyDate` | medium met tijdzone; low zonder tijdzone |

Een PDF-aanmaakdatum beschrijft vaak de PDF-export, niet noodzakelijk het oorspronkelijke
document. Daarom blijft provenance zichtbaar.

De parser accepteert naast ISO 8601 ook gangbare PDF-datumnotatie en bekende UTC-varianten
zoals `D:20250211174245Z00'00'`. De ruwe waarde blijft altijd bewaard.

## Temporal profile

`v_file_temporal_profile` geeft per actief bestand de beste huidige created/modified-
interpretatie. De view gebruikt alleen evidence voor de huidige `content_sha256`, toont
evidence-ID, bron en confidence en markeert conflicten. Onderliggende evidence wordt nooit
overschreven.

Exacte fysieke kopieën delen embedded evidence via hun `content_sha256`. Office/PDF-datums
worden daardoor niet per duplicate opgeslagen. Het waargenomen `file_id` blijft provenance,
maar is niet de identiteit van content-scope evidence.

Foreign keys verwijderen evidence niet via cascade. CORE gebruikt soft-delete; fysieke
verwijdering van een database-identiteit vereist daardoor eerst een expliciet retentiebesluit
voor het bijbehorende bewijs.

## Filesystemdatums en technische CORE-access

Synology File Station toont naast wijzigingstijd ook **Gemaakt op** en
**Laatst geopend**. Die labels zijn niet zonder provenance gelijk aan een
oorspronkelijke documentdatum of menselijke activiteit:

- een filesystem-aanmaak- of birthtime die na de inhoudelijke wijzigingstijd ligt,
  beschrijft bij een Cloud Sync-import doorgaans het ontstaan van de NAS-kopie;
- zo'n tijd hoort eventueel als file-scope `uploaded`/`synced` evidence te worden
  opgeslagen, nooit als content-scope `source_created_at`;
- filesystem `atime` beschrijft een read, maar identificeert niet wie of welk proces
  heeft gelezen;
- hashing, metadata-extractie, datum-backfill, semantic extraction en embedding kunnen
  zelf zo'n read veroorzaken en daarmee `atime` veranderen;
- een technische CORE-read wijzigt de documentinhoud, contenthash en `mtime` niet.

CORE zet `atime` niet terug: dat zou een nieuwe filesystemmutatie zijn en historische
informatie vervalsen. De beoogde oplossing is append-only activity evidence. Een CORE-run
legt eigen reads vast als bijvoorbeeld `core_hash_read`, `core_metadata_extract` of
`core_embedding_extract`, met `actor_scope=system`. Een atime-verandering die daarmee
samenvalt is technische access en geen `last_human_activity_at`.

Raw `atime` wordt pas opgenomen nadat een afgebakende pilot het Synology-mountbeleid en
de effecten van scanner, SMB, hashing en extractie afzonderlijk heeft gemeten. Zonder
betrouwbare correlatie blijft het hoogstens `actor_scope=unknown` met lage confidence.
SMB-audit- of applicatie-events met bron en actor kunnen later sterker human-accessbewijs
leveren.

## Runtime-integratie

Na een file-upsert extraheert Metadata Worker datum-evidence binnen dezelfde transactie.
Een ontbrekend oud schema wordt veilig overgeslagen. Een corrupte, onleesbare of beveiligde
bron geeft een waarschuwing en stuurt het verder geldige file-event niet naar de DLQ.

## Uitrol naar ACC

Voer na merge en pull eerst de migratie uit en bouw daarna Metadata Worker opnieuw:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260810_add_file_date_evidence.sql

docker compose build metadata_worker
docker compose up -d --force-recreate metadata_worker
```

Inventariseer bestaande documenten zonder writes:

```bash
core metadata date-backfill \
  --source /volume1/data/import/cloud/onedrive/current/Documenten \
  --dry-run
```

Pas de idempotente backfill daarna expliciet toe:

```bash
core metadata date-backfill \
  --source /volume1/data/import/cloud/onedrive/current/Documenten \
  --apply
```

Herhalen is database-idempotent: dezelfde observatie maakt geen tweede record en de
documentinhoud verandert niet. Het uitlezen van een bronbestand kan filesystem `atime`
wel bijwerken; dit is technische access en geen inhoudelijke bestandsmutatie.

## Verificatie

```sql
SELECT source_type, date_type, confidence, COUNT(*)
FROM file_date_evidence
GROUP BY source_type, date_type, confidence
ORDER BY source_type, date_type, confidence;

SELECT * FROM v_file_temporal_profile
WHERE evidence_count > 0
ORDER BY file_id DESC
LIMIT 25;
```

## Rollback

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/rollback/20260810_add_file_date_evidence.sql
```

Rollback verwijdert alleen de afgeleide evidence en view. Zet eerst de vorige Metadata
Worker-versie terug. Bronbestanden en `files`/`metadata` blijven intact.

## Vervolg

Media krijgt later providers voor EXIF en containerdatums zonder wijziging van het model.
De active-worksetengine consumeert de temporal-profileview in een afzonderlijke refinement.

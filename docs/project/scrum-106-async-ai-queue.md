# SCRUM-106 — asynchrone AI-wachtrij

## Doel

Een lokaal AI-voorstel kan per document worden aangevraagd, ongeacht of het
document actief, inactief of nog te beoordelen is. De portalrequest wacht niet
op het model. De aanvraag wordt duurzaam opgeslagen en door één afzonderlijke
worker verwerkt.

```mermaid
flowchart LR
    A["Vraag AI-voorstel aan"] --> B["Persistente wachtrij"]
    B --> C{"CPU, RAM en CORE-lag veilig?"}
    C -- "nee" --> B
    C -- "ja" --> D["Lokale AI-worker"]
    D --> E["Alarmbel: voorstel gereed"]
    E --> F["Mens controleert verschillen"]
    F --> G["Append-only menselijke events"]
```

## Prioriteit en begrenzing

De eerste versie verwerkt maximaal één taak tegelijk. Actieve documenten hebben
prioriteit 300, lifecycle-review 200 en inactieve documenten 100. Binnen één
prioriteit geldt de oudste aanvraag eerst.

De worker start geen volgende taak wanneer:

- genormaliseerde CPU-load boven `CORE_AI_MAX_CPU_PERCENT` ligt (standaard 70%);
- minder dan `CORE_AI_MIN_AVAILABLE_MIB` vrij geheugen resteert (standaard 3072 MiB);
- scanner-/metadata-streamlag hoger is dan `CORE_AI_MAX_STREAM_LAG` (standaard 1000).

Een wachtende job houdt een verklaarbare reason-code. De CORE-pipeline en portal
hebben altijd voorrang.

## Menselijke controle

De alarmbel toont nieuwe voorstellen. `Neem volledig AI-voorstel over` toont
eerst categorie, familie, privacy, lifecycle, confidence, reden, model en
promptversie. Na bevestiging schrijft CORE afzonderlijke append-only events voor
doelpad/classificatie, privacy en lifecycle. Het AI-resultaat zelf is geen
menselijk akkoord.

De worker en portal wijzigen, verplaatsen, hernoemen of verwijderen geen bestand.

## OCR-advies bij onleesbare inhoud

Voor de lokale AI wordt aangeroepen, probeert CORE eerst lokaal tekst uit het
document te halen. CORE raadpleegt daarvoor eerst bestaande `needs_ocr`-evidence
die bij exact dezelfde inhoudshash hoort. Als die evidence actueel is, wordt het
document niet opnieuw geopend en verschijnt `OCR vereist — reeds vastgesteld`,
inclusief lineage naar de eerdere semantic run.

Als nog geen evidence bestaat en een PDF of afbeelding geen herkenbare tekst oplevert,
wordt de AI-aanvraag controleerbaar afgerond met `OCR aanbevolen` en reason-code
`ocr_recommended_no_extractable_text`. Dit resultaat verschijnt zowel op de
documentkaart als in de alarmbel.

CORE start OCR niet automatisch. Na een gecontroleerde OCR-stap kan opnieuw een
AI-voorstel worden aangevraagd. Een leeg Word- of Excel-document krijgt alleen
`geen uitleesbare tekst`, omdat OCR daar normaal geen passende vervolgstap is.

## Uitrol

1. Migratie `20260816_add_async_workset_ai_jobs.sql` toepassen.
2. Dashboard en `workset_ai_worker` bouwen.
3. Begin met tien expliciete aanvragen en controleer wachtrijprioriteit en resourcegates.
4. Pas grenswaarden pas aan na observatie in acceptatie.

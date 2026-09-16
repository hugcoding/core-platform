# SCRUM-148 — load-bewuste AI/OCR-fallback

## Begrenzing

- Selectie: uitsluitend `effective_workset_status=inactive`, `review_state=pending` en
  `review_family=general`.
- Ontdekking: keyset-pagina's van maximaal 5 documenten, standaard elke 300 seconden.
- Backpressure: maximaal 5 open automatische AI-jobs en maximaal 10 nieuwe jobs per uur.
- Prioriteit: automatische inactieve jobs gebruiken prioriteit 100; handmatige actieve en
  `needs_review`-verzoeken blijven voorgaan.
- De Workset GET-route enqueue't niets en schrijft niet naar PostgreSQL.

## Pauzevoorwaarden

AI en OCR pauzeren bij hoge host-load, onvoldoende geheugen, scanner-streamachterstand,
meer dan vier andere actieve PostgreSQL-sessies, actieve gecontroleerde uitvoering,
Redis-uitval of onderhoudsmodus.

## Nulmeting 16 september 2026

- Restgroep op `nasdb_test`: 56 inactieve pending/general-documenten.
- Read-only selectie via `v_effective_document_workset`: circa 1,60 seconde op de NAS
  met warme buffers.
- Bij het standaardinterval wordt deze begrensde query maximaal tweemaal per uur gestart:
  circa 3,2 seconden databasewerk per uur voordat load-gating en backpressure verdere
  uitvoeringen overslaan.
- Acceptatiegrens: automatische ontdekking blijft onder 2 seconden met warme buffers en
  verandert de bestaande Workset GET-query niet.

## Verwerking

CORE gebruikt eerst lokale tekstextractie. Alleen een OCR-geschikt document zonder
voldoende tekst krijgt een content-gebonden Tesseract-job. De AI-job wacht zonder busy
loop op het OCR-resultaat en hervat daarna idempotent. Provider, model, promptversie,
confidence, evidence en OCR-lineage worden in bestaande audit-tabellen opgeslagen.
Geen voorstel wordt automatisch geaccepteerd.

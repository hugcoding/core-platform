# ASN-transactienummers en herstel van bestaande duplicaten

Een opnieuw gedownloade betaling met hetzelfde ASN-nummer hoort geen tweede
boeking of handmatige duplicaatvraag op te leveren. Het ASN-profiel gebruikt nu
`Ntry/NtryRef` als primaire identiteit binnen een rekening. Dit volgt de door de
beheerder bevestigde stabiliteit van dit nummer in ASN-downloads. `MsgId` en
statement-ID zijn downloadidentiteiten en worden hiervoor niet gebruikt.

## Beslisregels

- Sleutel: HMAC met domein `asn-ntryref-v1` over bestaand account-ID en de exacte
  getrimde `NtryRef`. Voorloopnullen blijven behouden. Rekeninggroepen en
  weergavenamen hebben geen invloed op deze identiteit.
- Alleen het ASN-profiel voor Nederlandse rekeningcodes ASNB/SNSB/RBRB gebruikt
  deze garantie. Andere banken en lege/placeholderreferenties houden de bestaande
  voorzichtige vergelijking; CAMT-syntax alleen is geen bankgarantie.
- Bekend nummer en gelijkblijvende betalingsgegevens: nieuwe bronregel koppelen
  aan de bestaande transactie; eenmaal tellen, geen reviewvraag.
- Nieuw nummer: aparte betaling, ook wanneer datum, bedrag en tekst gelijk zijn
  aan een andere betaling met een ander nummer. Een oude gelijkende regel zonder
  bruikbaar nummer blijft wel onzeker.
- Gelijke nummers met verschillende fingerprints blijven open. De fingerprint
  controleert boekdatum, valutadatum, bedrag, valuta, NFC-omschrijving en
  tegenrekening. CORE overschrijft geen bankinformatie bij een conflict.
- Meer dan een reeds gepubliceerde transactie voor hetzelfde nummer wordt niet
  automatisch samengevoegd. Eerdere handmatige oordelen blijven intact.
- Zelfde nummer op andere rekeningen blijft apart. Identieke bestandbytes blijven
  via de bestaande bestand-idempotency een replay. De parser/importversie wordt
  niet verhoogd; oude bestanden krijgen geen nieuwe importbatch.

## Herstel zonder opnieuw importeren

De UI-knop **Bestaande duplicaten herkennen** vraagt een `references`-job aan in de
bestaande Finance-queue. De worker leest uitsluitend lokaal de reeds versleuteld
bewaarde XML; de importmap is voor deze job niet nodig.

Eerst indexeert de worker alle bestaande bronregels, ook van teruggedraaide
imports. Locator, accountidentiteit en fingerprint worden tegen de bestaande
records gecontroleerd. Daarna verwerkt hij openstaande gevallen uit actieve
imports in blokken van maximaal 100. Eerst alles indexeren voorkomt dat een nog
niet gelezen oorspronkelijk nummer ten onrechte als nieuw wordt behandeld.

Bij een zekere match komt een bronkoppeling en een append-only duplicate-event
met actor `asn-ntryref-v1`. Een bewezen afzonderlijke betaling krijgt een nieuwe
transactie met dezelfde audit. Bestaande records, bronnen, transacties en reviews
worden niet aangepast of verwijderd. Importstatus/openstaande aantallen worden
met nieuwe events bijgewerkt. Herhalen of hervatten maakt geen dubbele oordelen.

Voor elke bron en elk blok geldt de bestaande resource/admission-check: CPU,
geheugen, PostgreSQL, CORE-pipeline en gecontroleerde uitvoering houden voorrang.
De bestaande Finance-heartbeat en queue in CORE Pulse blijven zichtbaar. De UI
toont **ASN-herkenning** onder Bronnen & imports en ververst tijdens verwerking.
Een andere lopende job moet eerst gereed zijn. Gewone nieuwe imports voeren deze
historische controle ook uit voordat nieuwe bestanden worden verwerkt.

De index (`finance_record_bank_references`) bewaart het nummer versleuteld en de
zoeksleutel als HMAC. `finance_reference_extractions` registreert welke batch is
gelezen. Tabellen zijn append-only, met account/source-relatiecontrole en
gescheiden API-/ingest-rechten. Geen AI, externe dienst of bankinhoud in logs.

De resterende vergelijking toont de binnengekomen regel naast bestaande
betalingen: datum, bedrag, tegenpartij, omschrijving, tegenrekening en ASN-nummer.
Details en bronnen van de bestaande betaling zijn bereikbaar. Een conflicterende
koppeling is geblokkeerd. Late UI-responses herstellen geen gegevens na sluiten
of vergrendelen. De melding spreekt over importregels: de oorspronkelijke
betaling kan al in de totalen staan.

## Uitrol op de NAS door de beheerder

Merge eerst de PR. Alle eerdere Finance-migraties, inclusief
`20260923_add_finance_bank_balances.sql` uit PR #212, moeten toegepast zijn.
De nieuwe migratie controleert die voorwaarde. Voer dit uit in de NAS-shell:

```bash
cd /volume1/docker/nas-stack
core git pull

export CORE_FINANCE_BUILD_CONTEXT=/volume1/docker/nas-stack
core_compose() {
  /usr/local/bin/docker compose -p nas --env-file .env \
    -f docker-compose.yml \
    -f tools/runtime/finance-compose.override.yml "$@"
}

core_compose build dashboard &&
/usr/local/bin/docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20260924_add_finance_bank_references.sql &&
core_compose up -d --no-build --no-deps dashboard finance_worker &&
core_compose ps dashboard finance_worker
```

De migratie is eenmalig. Bij een fout stopt de keten: eerst oplossen, niet alsnog
de containers vernieuwen. Dashboard en worker gebruiken hetzelfde gebouwde
image; beide moeten vernieuwd worden. Geen andere services herstarten.

Open Finance, **Ctrl+F5**, ontgrendel en klik **Bestaande duplicaten herkennen**
bij de melding over openstaande regels. Wacht op **ASN-herkenning: Gereed** onder
Bronnen & imports. Geen bestanden opnieuw downloaden of importeren. Alleen
resterende onzekere/conflicterende gevallen vragen daarna aandacht. De precieze
afname van de bestaande wachtrij is pas na lokale uitvoering bekend.

## Rollback en verificatie

De down-migratie in `database/migrations/rollback/20260924_add_finance_bank_references.sql`
weigert zodra referentiehistorie of een hersteljob bestaat. Bewaar dan schema en
audit en zet alleen de applicatie terug. Een oudere worker ondersteunt een
`references`-job niet: laat die eerst afronden voordat je applicatie terugzet.

Tests gebruiken uitsluitend synthetische XML en de aparte database
`core_finance_test`. Ze dekken unieke/gedeelde nummers, rekeningisolatie,
parallelle imports, bestand-replay, conflicten, originele betaling in de UI/API,
historisch herstel zonder nieuwe bronnen/batches, herhaald herstel, behoud van
handmatige oordelen, teruggedraaide bronnen, authenticatie, CSRF, append-only,
forward/down/up en wachten bij gecontroleerde uitvoering. UI-regressies bewaken
escaping, laadstatus en het wissen van gegevens bij vergrendelen.

# Terugkerend: gezamenlijk akkoord en volledige aantallen

De kaart toont maximaal 50 patronen per pagina. Open **Instellingen en betalingen bekijken** voor het totale aantal betalingen en de eerste en laatste boekingsdatum. De preview bevat maximaal 50 unieke betalingen verspreid over die volledige periode; het aantal in de preview beperkt het onderliggende totaal niet.

**Alles opslaan en akkoord** bevestigt de gekozen soort en eventueel de categorie/subcategorie in één database-transactie. Kies expliciet:

- Categorieën behouden: alleen de soort en het patroon bevestigen.
- Geselecteerde betalingen: uitsluitend aangevinkte betalingen uit de preview.
- Alle onderliggende betalingen: alle huidige betalingen van het patroon, ook buiten de preview.

Handmatig bevestigde classificaties blijven beschermd, tenzij de gebruiker expliciet overschrijven aanvinkt. Een gewijzigde bron of beoordeling maakt een open preview ongeldig: vernieuw eerst. Identieke retries zijn idempotent. Alle beoordelingen blijven append-only; bankboekingen en saldi worden niet gewijzigd.

Het overzicht opent op **Te beoordelen**. Na akkoord staat het patroon bij **Bevestigd**; opnieuw herkennen wist die beoordeling niet. Na samenvoegen vernieuwt het overzicht automatisch en wordt de samengestelde kaart zichtbaar.

## Bestaande aansluitpunten

De implementatie gebruikt de bestaande `v_transactions`, patroonlidmaatschappen, eigenaarbeveiliging, categorie-taxonomie en reviewtabellen. De gezamenlijke actie schrijft bestaande classificatie-events en een patroonreview atomair. Er is geen nieuwe tabel, migratie, queue of worker.

De bestaande scanbeveiliging van 25.000 betalingen blijft gelden. Een grotere groep geeft een duidelijke fout; er wordt geen gedeeltelijk akkoord opgeslagen.

## Uitrol

Na merge: werk main bij met `core git`, bouw en vervang alleen dashboard en vernieuw de browser volledig. Er is geen nieuwe migratie of herimport nodig. De PR bevat de exacte NAS-commando's.

## Validatie

58 geïsoleerde databasetests met fictieve CAMT-data slagen, inclusief retries, conflicts, rollback, handmatige bescherming en filters na herdetectie. Vijf UI-testsuites slagen voor selectie, context, laden, gezamenlijk akkoord en automatisch verversen na samenvoegen.

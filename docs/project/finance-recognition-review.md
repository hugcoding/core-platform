# Eigen herkenningsregels en accorderen (SCRUM-165 / basis SCRUM-164)

## Meteen accorderen in het startoverzicht

Bij ingebouwde herkenners staan selectie en Selectie accorderen direct bij de
resultaten. Je hoeft niet eerst Nieuwe regel of Als eigen regel bewerken te
openen. Kies voorbeelden of Alle te accorderen transacties. Ook een al correcte
automatische indeling is te bevestigen; een identieke handmatige bevestiging
wordt niet opnieuw aangemaakt. Afwijkende handmatige beoordelingen blijven
beschermd. De voorgestelde uitkomst staat bij CORE vult aan.

De bestaande preview-, snapshot-, bulk-review- en idempotentiefuncties worden
hergebruikt. Een inactief intern auditrecord legt de gebruikte ingebouwde
definitie vast; het verschijnt niet als eigen regel en wordt nooit actief in de
worker. De ingebouwde herkenner blijft ongewijzigd. Deze uitbreiding vereist
geen extra migratie bovenop 20261025_add_finance_recognition_review.sql.

Finance → Eventherkenner laat de ingebouwde herkenners intact. Kies Nieuwe regel,
Als eigen regel bewerken bij een ingebouwde herkenner, of open een opgeslagen
eigen regel. Bij ASN worden issuer/code als voorwaarden overgenomen; complexe
ingebouwde logica blijft alleen-lezen. Bij overige herkenners stel je zelf de
voorwaarden in. Je kunt voorwaarden combineren met alle of minimaal één.

Formulier en Regelcode bewerken dezelfde declaratieve JSON-definitie. De JSON
bevat module, naam, actief, when (all/any met field/op/value), set en optioneel
exclude. Alleen equals en begrensde contains zijn toegestaan; geen regex/eval,
scripts, bestandsbewerkingen of willekeurige acties. Het formulier gebruikt de
bestaande Finance-categorieën; codes in de regelcode zijn dezelfde codes.

## Eén samenhangende beoordeling

Vink alleen de velden aan die je wilt wijzigen: tegenpartij, categorie en/of
transactiesoort. Een tegenpartij kan zelfstandig worden bevestigd als de
categorie al correct is. Een ontbrekende merchant kan worden aangevuld terwijl
een handmatig bevestigde categorie intact blijft. Een bestaande handmatige
naam of afwijkende handmatige categorie wordt niet via bulk overschreven;
gebruik daarvoor bewust Bekijk / wijzig handmatig in de bestaande details.

Accorderen gebruikt het bestaande model waarin de getoonde volledige indeling
als eigenaarbeoordeling wordt bevestigd; alleen aangevinkte veldwaarden veranderen.
Bij een nog automatische transactie zonder categorie vraagt de voorbeeldcontrole
ook een categorie voordat je bevestigt. Zo wordt een lege categorie niet door
een naambevestiging onbedoeld vastgezet. Automatische regels kunnen de naam wel
afzonderlijk aanvullen en laten de resterende categorieherkenning beschikbaar.

Voorbeelden controleren toont het volledige aantal matches (binnen de bestaande
directe grens van 25.000 actieve transacties) en maximaal 50 voorbeelden over de
periode, met huidige gegevens en wijzigingen per veld. Kies Mijn selectie of
Alle passende wijzigbare transacties; die laatste keuze is onafhankelijk van
de 50 getoonde voorbeelden. Opslaan en accorderen bewaart de regelversie en
beoordelingen in één transactie. Alleen regel opslaan verandert geen boekingen.

Selectie beperkt de huidige accordering. Uitsluiten van regel bewaart een
transactie-ID in de versleutelde regel; deze transactie matcht daarna niet meer.
Uitsluitingen kunnen worden hersteld of als JSON aangepast. De voorwaarden
blijven bepalend voor nieuwe matches: selectie traint geen verborgen model.

Het preview-snapshot en de vorige regelversie worden bij opslaan opnieuw
gecontroleerd. Wijzigingen in transacties, imports of beoordelingen vereisen een
nieuwe controle. Herhaald indienen met dezelfde sleutel herhaalt geen effecten.
Een verloren antwoord kan met dezelfde sleutel worden herhaald. Sluiten en
vergrendelen wissen formulier, regelcode, voorbeelden en verzoekstatus; late
antwoorden worden genegeerd. De nieuwe versie staat in de classificatiehistorie.

## Hergebruik en automatische toepassing

core/recognition/rules.py is de gedeelde, I/O-vrije validator en matcher. Finance
levert een adapter met bestaande bankmetadata, encryptie, categorievalidatie,
rekeninglabels en reviewfuncties. Het gedeelde formaat kent ook Werkset-velden,
maar Werkset-opslag, acties en UI zijn nog niet aangesloten: die volgen onder
SCRUM-164. Finance accepteert geen Werkset-regels en ontsluit geen gegevens aan
Werkset. Er zijn geen wijzigingen aan eigenaarbeveiliging, .env of secrets.

Actief betekent toepassen tijdens de volgende bestaande CORE-indelingsrondes,
ook op later geïmporteerde transacties. Een import start niet zelfstandig een
LLM- of classificatiejob. Start de bestaande indelingsronde zelf, desgewenst met
LLM uit. Actieve regels gebruiken dezelfde plan-functie als de voorbeeldcontrole.
De daadwerkelijke boekingen gebruiken de bestaande worker en centrale capaciteit.
Handmatig bevestigde transacties worden automatisch nooit gewijzigd. Gelijke
acties zijn idempotent; tegenstrijdige actieve regels leiden tot onthouding,
niet tot een willekeurig gekozen winnaar. Algemene regelvoorstellen en een
conflictdashboard blijven vervolgstappen.

Eigen regels kunnen categorie/naam aanpassen op automatische indelingen, maar
kunnen geen eigen-overboekingtype afdwingen. Reversals, meerdere transactiedetails
en tegenstrijdig ASN-bankbewijs worden niet blind verwerkt. Categorieën moeten
actief en correct gekoppeld zijn. Regelkennis en categorieën worden per wijzigings-
versie gecachet; bronbewijs wordt bij voorbeeldcontrole gebundeld opgehaald.

## Opslag en uitrol

Nieuwe tabel finance.finance_recognition_rule_events bewaart append-only en
versleuteld de definities. finance_review_events.recognition_rule_event_id
verwijst naar de gebruikte versie. Bestaande tegenpartijen, classificatiehistorie,
optimistic locking en bulk-review-insert worden hergebruikt. Alleen Finance API
mag regels opslaan; de worker leest actieve versies. Databasebeveiliging bewaakt
ook bij automatische toepassing een actieve actuele regel en beschermt owner-
reviews. Terugdraaien van de migratie weigert zodra regels bestaan.

Na merge op de NAS (oorspronkelijke Eventherkenner-migratie al uitgevoerd):

```sh
cd /volume1/docker/nas-stack
core git pull --skip-docs
docker exec -i postgres sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' < database/migrations/20261025_add_finance_recognition_review.sql
core finance deploy
core finance status
```

Voer de migratie vóór nieuwe dashboard/worker-code uit; stop bij fouten. Nieuwe
code verwacht de nieuwe kolom/tabel. De migratie zelf wijzigt geen bankboekingen.
Na deployment Ctrl+F5. Controleer een eigen ASN-regel met alleen tegenpartij,
een reeds juiste categorie, een selectie en een beschermd handmatig oordeel.
Controleer ook opslaan zonder boekingen, JSON-bewerking en een nieuwe lokale
indelingsronde met LLM uit. Originele bankgegevens blijven zichtbaar.

## Testen

Alle fixtures zijn fictief; geen echte transacties, exports of productiegegevens.
De PostgreSQL-suite vereist expliciet een geïsoleerde core_finance_test-database.
Unit tests: tests.test_recognition_rules. De bestaande Finance-integratiesuite
test migratie/rollback, encryptie, owner-only, versieconflicten, snapshots,
selectie/alles, handmatige bescherming, idempotentie en actieve/uitgeschakelde
regels in de bestaande job. UI-tests gebruiken de echte pagina met fictieve
HTTP-antwoorden, inclusief formulier, JSON, uitsluiting en sessievergrendeling.

```sh
node tests/test_finance_event_recognition_ui.cjs
node tests/test_finance_event_recognition_page.cjs
```

De laatste test vereist Playwright en een browser; bij lokale Edge kan
CORE_TEST_BROWSER_CHANNEL=msedge gebruikt worden.

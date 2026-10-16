# Terugkoppeling bij Vernieuwen

De bestaande knop Vernieuwen haalt direct gegevens op. Omdat ongewijzigde
transactierijen behouden blijven en de laadmelding meteen werd gewist, was
niet duidelijk of de controle was uitgevoerd.

De knop toont nu tijdens de aanvraag Bezig... en is tijdelijk uitgeschakeld.
Na een geslaagde aanvraag blijft 'Overzicht gecontroleerd om [tijdstip]' zichtbaar,
ook als er geen gewijzigde rijen zijn. Het tijdstip gebruikt de lokale browsertijd.
De melding beweert niet dat er nieuwe transacties zijn gevonden. Bij een mislukte
aanvraag verschijnt een foutmelding en is opnieuw proberen mogelijk.

Een oudere aanvraag overschrijft geen nieuwere filterstatus. Een vergrendelde
sessie krijgt geen achterhaalde succesmelding; de knop wordt bij vergrendelen
hersteld. De vijfminutencontrole en de rustige transactieweergave blijven behouden.
Geen wijziging aan API, database, worker, financiële gegevens of secrets.

## NAS-uitrol

Merge deze PR. Voor de onderstaande korte uitrol moet ook de eerdere PR van
codex/finance-deploy-cli met core finance deploy gemerged zijn.

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
core finance deploy
core finance status
```

Stop bij fouten; bewaar of commit eventuele lokale wijzigingen voordat je pullt.
Geen migratie nodig. Vernieuw de browser na deployment met Ctrl+F5. Klik Vernieuwen:
Bezig... verschijnt, daarna de controlebevestiging met tijdstip. De ongewijzigde
rijen blijven staan. Bij een fout moet de knop opnieuw beschikbaar zijn.

Tests gebruiken fictieve UI-status en gecontroleerde promises voor dubbele
klikken, succes, fout, nieuwere filters en sessievergrendeling. De bestaande
rustige verversing, afhankelijke filters, faseweergave en LLM-toggle zijn eveneens
gecontroleerd. Geen productiegegevens gelezen en niets gedeployd.

# Project Documentation

Deze sectie ontsluit de projectdocumentatie binnen de MkDocs-site.

## Bronnen

De repository bevat de volgende projectartefacten:

| Locatie | Inhoud |
|---|---|
| `project/PROJECT_STATUS.md` | Gegenereerde projectstatus en inventarisatie |
| `project/issues/` | Lokale issuebeschrijvingen |
| `project/epics/` | Epicdocumentatie |
| `project/releases/` | Releasebeschrijvingen |
| `project/sprints/` | Sprintdocumentatie |
| `project/reports/` | Onderzoeks- en beslisrapporten |
| `project/exports/` | Jira- en operationele exports |

Jira is de actuele bron voor planning en issue-status. De repository bewaart technische rapporten, migratieplannen en gegenereerde snapshots die samen met code moeten worden gereviewd.

## Actuele database-evolutie

De eerste read-only fase van SCRUM-53 inventariseert het PostgreSQL-schema en classificeert mogelijke opruimkandidaten. Bekijk [SCRUM-53 Database Review](scrum-53-database-schema-review.md) voor de bevindingen en het gecontroleerde vervolgplan.

De actuele lokale LLM-classificatiepilot, ACC-opslag, menselijke reviewgrens en
de afspraak over Engelse technische codes met Nederlandse labels en fysieke
doelpaden staan in [SCRUM-85 Persoonlijke LLM-classificatie](scrum-85-personal-llm-classification.md).

De read-only selectie van DOCX- en XLSX-golden records voor een dynamische
werkset staat in [SCRUM-89 Actieve werkset pilot](scrum-89-active-workset-pilot.md).

De read-only databasegroeimeting en contractgrenzen voor operationele, semantic-
en classificatiedata staan in
[SCRUM-78 Databasegroei en contractgrenzen](scrum-78-database-growth-review.md).

De actuele OneDrive-werkset wordt los van de historische NAS-data beoordeeld.
Bekijk [SCRUM-76 OneDrive-baseline en golden-recordreview](scrum-76-onedrive-baseline.md)
voor bronautoriteit, exacte matching, ruimtebesparingsbovengrenzen en de veilige
reviewflow.

Statische documentdatums worden generiek en append-only opgeslagen, los van
`metadata.created_at`. Bekijk [SCRUM-69 Datum-evidence en provenance](scrum-69-date-evidence.md)
voor het uniforme Office/PDF-contract, de temporal-profileview en de backfillprocedure.

## Projectworkflow

Ontwikkel en commit vanuit de lokale workspace:

```powershell
cd C:\Development\nas-stack
git status
git add <bestanden>
git commit -m "Beschrijving"
git push origin main
```

Werk daarna de deployment-checkout veilig bij:

```powershell
.\tools\windows\core.ps1 git pull
```

Zie [Operations](../wiki/operations.md) voor Docker Compose-deployment, databasebackup en runtimecontrole.

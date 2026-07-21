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

# SCRUM-116 — gecontroleerde uitvoerwachtrij

CORE brengt cleanup en persoonlijke migratie samen in één menselijke
goedkeuringsflow. Kandidaten blijven inhoudelijk verschillende actietypen; alleen
de selectie, batchstatus en voortgang gebruiken hetzelfde contract.

## Prioriteit

1. exacte duplicaten naar quarantaine;
2. menselijk beoordeelde inhoudelijk vergelijkbare PDF's naar quarantaine;
3. verwijderreviews naar quarantaine;
4. reguliere migratie naar Actief;
5. reguliere migratie naar Inactief.

Een file-ID komt maximaal één keer in een batch. De actie met de laagste
risicoprioriteit wint. Een batch bevat maximaal 25 bestanden.

## Controlegrens

De read-only inventaris vult uitsluitend een voorstel. Na selectie ontstaat een
immutable batch met een evidence-snapshot. Goedkeuring en alle workerstatussen
zijn append-only events. Bestanden worden nooit permanent verwijderd.

```mermaid
flowchart LR
  A[Candidate views] --> B[Read-only queue]
  B --> C[Maximaal 25 selecteren]
  C --> D[Menselijk akkoord]
  D --> E[Immutable batch]
  E --> F[Achtergrondworker]
  F --> G[Hash en doel opnieuw controleren]
  G --> H[Verplaatsen en verifiëren]
  H --> I[Watcher-event correleren]
  I --> J[Resultaat en rollback]
```

## Eerste slice

De eerste slice levert het databaseschema, deterministische prioritering en een
read-only CLI-inventaris:

```bash
core workset execution-queue --limit 25 --dry-run
```

Deze opdracht schrijft niets en verplaatst geen bestanden. Vervolg-slices voegen
dashboardselectie, expliciete accordering, één resource-aware worker,
voortgangsweergave, notificatie, reconcile en rollback toe.

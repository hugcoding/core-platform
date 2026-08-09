# CORE-ketendiagrammen

Deze pagina legt de belangrijkste CORE-stromen versieerbaar vast. De diagrammen
tonen de huidige acceptatieomgeving en de geplande grenzen. Een pijl betekent
niet automatisch dat een component schrijfrechten heeft; expliciete
review- en apply-stappen blijven leidend.

## Ingest en operationele metadata

OneDrive blijft de gebruiksvriendelijke werklaag. Synology Cloud Sync brengt de
geselecteerde documenten read-only de CORE-importstroom in. Scanner en watcher
zijn twee verschillende signaleringsmechanismen; Redis ontkoppelt signalering van
duurzame verwerking.

```mermaid
flowchart LR
    OD["OneDrive<br/>laptop en iPhone"] -->|"Cloud Sync: download"| IR["NAS importroot<br/>/volume1/data/import/cloud/onedrive/current"]
    IR --> SC["Polling scanner<br/>full en interval"]
    IR -.-> WA["Watcher<br/>optioneel / policy"]
    SC --> RS["Redis Stream<br/>scan_stream"]
    WA --> RS
    RS --> MW["Metadata Worker"]
    MW --> PG[("PostgreSQL<br/>files en technische metadata")]
    MW -->|"niet-verwerkbaar event"| DLQ["scan_stream_dlq"]
    DLQ -->|"gecontroleerde replay"| RS
```

Zie ook [Scanner](scanner.md), [Metadata Worker](metadata-worker.md),
[Redis](redis.md) en [Operations](operations.md).

## Golden records en semantische verwerking

Bestandshashes bepalen exacte inhoudsgelijkheid. Golden-recordselectie kiest de
representant van een contentgroep; mutatiedatum is daarvoor niet leidend.
Extractie en embeddings zijn afgeleide, herbouwbare gegevens.

```mermaid
flowchart LR
    F[("files")] -->|"volledige SHA-256"| CG[("content_groups")]
    CG --> GR["Golden record<br/>kwaliteit en integriteit"]
    GR --> EX["Lokale tekstextractie<br/>origineel blijft ongewijzigd"]
    EX --> CH[("semantic_chunks<br/>metadata, geen ruwe tekst")]
    CH --> EM[("embeddings ACC<br/>multilingual-e5-small")]
    EM --> HR["Hybrid retrieval<br/>vector + lexical + metadata"]
    HR --> RAG["Lokale RAG<br/>bronverwijzingen + abstention"]
    RAG --> OUT["Read-only antwoord<br/>geen autonome actie"]
```

De implementatie en meetresultaten staan in
[SCRUM-59 OneDrive Semantic Pilot](../project/scrum-59-onedrive-semantic-pilot.md).

## Classificatie, review en current-view

De lokale LLM levert uitsluitend een voorstel. Technische codes blijven Engels;
Nederlandse labels en fysieke doelpaden worden via een versieerbaar padbeleid
afgeleid. Alleen het nieuwste expliciet geaccepteerde besluit voor een nog
actueel golden record verschijnt in de current-view.

```mermaid
flowchart TD
    SEL["Representatieve golden-recordselectie"] --> LLM["Lokale LLM-classificatie"]
    LLM --> CAN["Canoniek contract<br/>Engelse technische codes"]
    CAN --> PROP[("classification_proposals<br/>pending_review")]
    PROP --> POL["Padbeleid<br/>Nederlandse labels en fysieke paden"]
    POL --> REV{"Menselijke review"}
    REV -->|"accepted / corrected"| AR[("append-only classification_reviews")]
    REV -->|"rejected"| RR[("append-only classification_reviews")]
    AR --> CUR[("v_current_file_classification")]
    CUR -->|"alleen na afzonderlijke autorisatie"| PLAN["Toekomstig copy/move-plan"]
    RR -.-> PROP
```

Details staan in
[SCRUM-85 Persoonlijke LLM-classificatie](../project/scrum-85-personal-llm-classification.md).

## Actief, archief, review en cleanup

Classificatie en lifecycle leveren advies. Bestandsmutaties, retentie en
verwijdering zijn afzonderlijke processen met expliciete autorisatie en fallback.

```mermaid
flowchart TD
    C["Geaccepteerde classificatie"] --> D{"Lifecyclebesluit"}
    D --> A["Actief<br/>recente of blijvend relevante werkset"]
    D --> H["Archief<br/>bereikbaar historisch materiaal"]
    D --> R["Beoordelen<br/>twijfel, conflict of lage confidence"]
    D --> Q["Quarantaine<br/>leeg, corrupt of versleuteld"]
    H --> T["Bewaartermijn verstreken"]
    T --> DR["Delete-reviewlijst"]
    DR -->|"bewaren"| H
    DR -->|"snapshot vereist"| HB["Offline Hyper Backup-archief"]
    HB -->|"expliciete goedkeuring"| X["Bronbestand verwijderen<br/>basisinformatie behouden"]
    DR -->|"afwijzen"| X
```

Geen pijl in deze flow autoriseert op zichzelf een move of delete.

## OTAP-promotie

Ontwerp en ontwikkeling starten lokaal. Acceptatie mag gecontroleerde metadata in
de ACC-database schrijven. Productie ontvangt uitsluitend gereviewde,
reproduceerbare wijzigingen; documentatie wordt alleen op expliciet verzoek
gedeployed.

```mermaid
flowchart LR
    O["O - Ontwikkeling<br/>lokale branch"] -->|"tests + documentatie + Git"| PR["Pull request"]
    PR -->|"review en merge"| A["A - Acceptatie<br/>nasdb_test"]
    A -->|"functionele review + migratiebewijs + go/no-go"| P["P - Productie"]
    A -->|"bevinding"| O
    P -->|"monitoring en incidentfeedback"| O
    DOC["MkDocs bron in Git"] -->|"expliciet: core docs deploy"| WIKI["Permanente Wiki"]
```

Zie [SCRUM-84](https://hugohoogendoorn.atlassian.net/browse/SCRUM-84) voor de
documentatieopdracht en [SCRUM-85](https://hugohoogendoorn.atlassian.net/browse/SCRUM-85)
voor de actieve classificatiepilot.

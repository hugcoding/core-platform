\# CORE Project Status



\*\*Project:\*\* NAS Metadata Platform



\*\*Platform Version:\*\* CORE 2.2 (In Progress)



\*\*Project Status:\*\* Active



\*\*Last Updated:\*\* 2026-07-10



\---



\
## Current Engineering Notes

- PROJECT-005 Jira Synchronization Engine started with a read-only foundation slice.
- Added CORE Jira commands for auth, epics/stories dry-run, read-only fetch and local cache.
- No Jira write/synchronization mutations are enabled in this slice.
# Executive Summary



Het NAS Metadata Platform is ontwikkeld van een verzameling losse scripts naar een modulair, zelfdocumenterend platform met een duidelijke scheiding tussen runtime, governance, documentatie, projectbeheer en kwaliteit.



De belangrijkste mijlpalen zijn:



\- Polling Scanner geïmplementeerd

\- Metadata Worker gestabiliseerd

\- Redis Streams als eventbus

\- PostgreSQL als centrale metadata-opslag

\- Documentation Engine ontwikkeld

\- Integrity Engine geïntroduceerd

\- Health \& Heartbeat monitoring toegevoegd

\- Standards Engine gebouwd

\- Project Intelligence Engine Foundation opgezet

\- Platform- en Projectmanifest geïntroduceerd



\---



\# Project Architecture



Het platform bestaat uit vijf hoofddomeinen.



\## Runtime



Verantwoordelijk voor het verwerken van bestanden.



Componenten



\- Scanner

\- Metadata Worker

\- (Dispatcher - gepland)

\- (Job Engine - gepland)



\---



\## Documentation



Verantwoordelijk voor automatische documentatie.



Componenten



\- Documentation Generator

\- Wiki Generator

\- DOCX Generator

\- JSON Analyse



\---



\## Governance



Verantwoordelijk voor architectuur en standaarden.



Componenten



\- Standards

\- RFC

\- ADR (in ontwikkeling)



\---



\## Quality



Verantwoordelijk voor kwaliteit en integriteit.



Componenten



\- Integrity Engine

\- Health Engine

\- Heartbeats



\---



\## Project



Verantwoordelijk voor planning en projectbeheer.



Componenten



\- Project Manifest

\- Roadmap

\- Releases

\- Jira Export (in ontwikkeling)

\- Dashboard (gepland)



\---



\# Manifesten



\## Platform Manifest



Locatie



core/core.yaml



Doel



Beschrijving van de software.



\---



\## Project Manifest



Locatie



project/meta/project.yaml



Doel



Beschrijving van roadmap, releases, epics, features, sprints en projectstructuur.



\---



\# Sprintoverzicht



\## Sprint 1 — Historical Foundation



Status



Released



Doel



Historisch vastleggen van alle werkzaamheden vóór de introductie van Jira.



Belangrijkste resultaten



\### Runtime



\- Polling Scanner

\- Metadata Worker

\- Redis Streams



\### Database



\- PostgreSQL

\- Schema

\- Integrity View



\### Documentation



\- Documentation Generator

\- Wiki

\- JSON

\- DOCX



\### Governance



\- Standards Engine

\- CORE Manifest



\### Quality



\- Health Engine

\- Heartbeats



\### Infrastructure



\- Docker tooling

\- Status scripts

\- Rebuild tooling



\---



\## Sprint 2 — Governance \& Project Intelligence Engine



Status



In Progress



Doel



CORE begrijpt zijn eigen architectuur, documentatie en projectstructuur.



Opgeleverd



\- Project structuur

\- Project Manifest

\- Standards documentatie

\- Documentation Engine uitbreiding



In uitvoering



\- ADR Engine

\- Project Analyzer

\- Dashboard Generator

\- Jira Export



\---



\# Releases



\## CORE 2.1 Foundation



Status



Released



Belangrijkste onderdelen



\- Scanner

\- Metadata Worker

\- Integrity Engine

\- Documentation Engine

\- Standards Engine

\- Health Engine



\---



\## CORE 2.2 Governance



Status



In Progress



Belangrijkste onderdelen



\- Project Intelligence Engine

\- Governance

\- ADR Engine

\- Jira Export

\- Dashboard



\---



\## CORE 2.3 Stabilization



Status



Planned



Doel



Legacy analyseren en gecontroleerd opruimen.



\---



\## CORE 2.4 Runtime Evolution



Status



Planned



Doel



Dispatcher en Job Platform introduceren.



\---



\## CORE 2.5 Intelligence



Status



Planned



Doel



Project Intelligence, dashboards en statistieken.



\---



\## CORE 3.0



Status



Vision



Doel



Volledig geïntegreerd metadata-platform.



\---



\# Belangrijkste Architectuurbeslissingen



\## Polling Scanner



Vanwege beperkingen van Synology is gekozen voor polling in plaats van inotify.



\---



\## PostgreSQL is Source of Truth



Alle metadata wordt centraal opgeslagen in PostgreSQL.



\---



\## Redis Streams



Scanner en workers communiceren via Redis Streams.



\---



\## Integrity First



Geen automatische verwijderingen.



Werkwijze:



Analyse → Dry Run → Apply



\---



\## Documentation as Code



Documentatie wordt automatisch gegenereerd.



\---



\## Markdown as Source



Projectinformatie wordt opgeslagen in Markdown.



Vanuit Markdown worden gegenereerd



\- Wiki

\- Dashboard

\- Jira CSV

\- Release Notes



\---



\# Huidige Status



Runtime



✔ Stabiel



Database



✔ Stabiel



Documentation



✔ Operationeel



Governance



🚧 In ontwikkeling



Project Intelligence Engine



🚧 Foundation gereed



Legacy



📋 Nog te analyseren



\---



\# Roadmap



Sprint 2



\- ADR Engine

\- Project Analyzer

\- Dashboard

\- Jira Export



Sprint 3



\- Legacy Assessment

\- Repository Audit

\- Database Audit

\- Docker Audit

\- Redis Audit



Sprint 4



\- Controlled Cleanup



Sprint 5



\- Dispatcher



Sprint 6



\- Job Engine



Sprint 7



\- Intelligence Platform



Sprint 8



\- Database Evolution



Sprint 9



\- Developer Experience



Sprint 10



\- CORE 3.0



\---



\# Visie



Het doel van CORE is niet alleen een metadata-platform te bouwen, maar een platform dat zichzelf begrijpt.



De belangrijkste principes zijn:



\- Platform before Features

\- Integrity First

\- Documentation as Code

\- Markdown as Source

\- Governance by Design

\- Project as Code

\- Self Documenting Platform



\---



\# Volgende Mijlpaal



Sprint 2 wordt afgesloten zodra:



\- ADR Engine gereed is

\- Project Analyzer gereed is

\- Dashboard Generator gereed is

\- Jira Export werkt

\- Eerste automatische Jira-import succesvol is uitgevoerd


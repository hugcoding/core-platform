# Indeling: eerst CORE, daarna de lokale LLM

Een categorisatieopdracht verwerkt de vastgelegde startselectie in twee fasen.

1. **CORE-herkenning** loopt eerst over alle nog openstaande targets. Bestaande menselijke beoordelingen en deterministische merchant-regels worden toegepast zonder de modelserver aan te roepen. Betalingen die een model nodig hebben blijven open voor fase twee. Tegenstrijdige menselijke voorbeelden worden niet door AI opgelost.
2. **Lokale LLM** verwerkt alleen die resterende targets, met de bestaande gedeelde groepscontext, begrensde caches en maximaal 200 targets per capaciteitscontrole. Ook hier wordt menselijke evidence opnieuw gecontroleerd; jouw nieuwere oordeel blijft leidend.

Fase en CORE-cursor staan in de bestaande `finance_ingest_jobs`. De cursor en beoordelingen worden in dezelfde batchtransactie opgeslagen. Na herstart of een capaciteitspauze blijft de voortgang beschikbaar. Een fasewisseling krijgt een commit voordat de eerste LLM-aanroep begint.

Als de laptop/modelserver onbereikbaar is, blijft de opdracht `pending` met `waiting_reason=waiting_for_local_llm`. CORE-resultaten blijven intact; de bestaande worker probeert later opnieuw zodra capaciteit beschikbaar is. Dit gebruikt niet het definitieve maximum voor algemene servicefouten. Stoppen blijft mogelijk en de stopstatus wordt niet overschreven. Er is geen cloudfallback.

De UI toont CORE-herkenning of Lokale LLM. De teller 'verwerkt' telt definitieve resultaten; targets die tijdens CORE worden doorgeschoven naar de LLM tellen pas mee nadat ook die beoordeling is afgerond.

## Deployment

Gebruik de NAS-stappen in de PR. Stop de Finance-worker, pas `20261005_add_finance_categorization_phases.sql` toe, bouw dashboard en Finance-worker, en vervang beide containers. Geen herimport of wijziging aan bestaande categorieen nodig. Een al mislukte opdracht wordt niet automatisch heropend; start daarvoor eenmaal een nieuwe categorisatieopdracht.

## Rollback

Stop de worker en zet actieve categorisatieopdrachten via de bestaande UI op gestopt. Zet vervolgens beide services terug naar de vorige codeversie voordat de rollback-migratie wordt toegepast. De rollback weigert actieve categorisatieopdrachten en verwijdert alleen fase/cursor-metadata. Bestaande targets, resultaten en append-only reviewevents blijven behouden.

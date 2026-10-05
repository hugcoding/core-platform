# Lokale indeling in groepen

De knop **Ongecategoriseerde betalingen indelen** maakt een bestaande Finance-queueopdracht voor betalingen zonder categorie. Bestaande automatische ?n handmatige categorie?n blijven behouden. Jouw correcties hebben voorrang en worden via de bestaande soortgelijke-betalingenmatcher hergebruikt.

Voor herkende winkels en OVpay gebruikt CORE de bestaande deterministische merchant-identiteit. Wisselende bankreferenties, betaaldata en bedragen leiden daardoor niet tot afzonderlijke LLM-vragen. Algemene tegenpartijen behouden hun beperkte, geredigeerde omschrijving: huur en een cadeau aan dezelfde ontvanger mogen niet ??n AI-groep worden. Richting, rekening en valuta worden bij hergebruik van classificatiebesluiten onderscheiden.

Per groep wordt eerst menselijke evidence gezocht. Tegenstrijdige menselijke beoordelingen leiden tot onthouding. Zonder bruikbaar oordeel beoordeelt de lokale LLM de gedeelde context; voldoende zekere antwoorden worden hergebruikt. Geen nieuwe cloudservice, matcher, queue of database nodig.

De worker verwerkt maximaal 200 bestaande targets per capaciteitscontrole en doet maximaal ??n nieuwe LLM-aanroep binnen zo'n batch. Besluiten en antwoorden worden begrensd in geheugen gecachet. Herstart, gewijzigde menselijke beoordelingen of cacheverwijdering kunnen herbeoordeling veroorzaken; dit is geen permanente AI-regel. Elke betaling krijgt haar eigen append-only event en idempotente resultaatregistratie. De bestaande stop-, race- en privacybeveiliging blijft actief. Onzekere betalingen blijven zonder categorie.

## Uitrol en controle

Geen migratie of herimport. Na merge dashboard ?n finance_worker herbouwen en vervangen; de worker bevat de groepslogica. Volledig browser vernieuwen. Start de knop opnieuw na een eerder gestopte opdracht. Controleer dat alleen ontbrekende categorie?n worden aangevuld en jouw beoordelingen behouden blijven. Voortgang blijft in aantallen betalingen zichtbaar, inclusief overgeslagen en onthouden betalingen.


## CORE eerst, LLM daarna

De opdracht rondt eerst alle CORE-herkenning af. Alleen het restant gaat naar de lokale LLM. Zie [fasen, hervatten en migratie](finance-core-before-llm.md). Voor deze fase-uitbreiding is de nieuwe migratie van 2026-10-05 nodig.

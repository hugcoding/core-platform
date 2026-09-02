# AI-status polling: PostgreSQL-belasting

De aangeleverde meting toonde gelijktijdige Werkset-query's met circa
60/45/30/15 seconden looptijd. De AI-statusroute voerde WORKSET_SELECT uit
terwijl de browser elke 15 seconden een nieuw verzoek startte.

Deze wijziging vervangt de verrijkte query door zes benodigde velden uit de
bestaande Werkset-view, met dezelfde hashfilter. Lidmaatschap en het opnieuw
koppelen van een voorstel aan de huidige file-ID blijven behouden.

De browser deelt een lopend verzoek, wacht op beide AI/OCR-antwoorden (ook
bij fouten) en start pas 15 seconden na afronding opnieuw. Verborgen tabbladen
starten geen nieuwe ronde. Er is geen database-migratie of datawijziging.

## Verificatie

- Python: `python -m pytest tests/test_dashboard_workset.py tests/test_workset_ai_queue.py -q`
- JavaScript: `node tests/test_ai_status_polling.cjs`
- Na merge/pull: `docker compose up -d --no-deps --build dashboard`.
- Vernieuw bestaande tabbladen zodat de nieuwe JavaScript-code geladen is.
- Herhaal de rustmeting, laden van één Werkset en meting na één minuut.
- Controleer pg_stat_activity: geen opstapeling van de verrijkte query per 15 seconden.

Niet bewezen door unit-tests: de uitvoeringstijd van de onderliggende databaseview
op productie. Ook de initiële Werkset-query en polling door meerdere gelijktijdige
gebruikers vallen buiten deze gerichte reparatie. Als de belasting hoog blijft,
onderzoek eerst de resterende actieve query's en hun uitvoeringsplan.

# SCRUM-98 gecontroleerd leren uit portalbeoordelingen

CORE normaliseert menselijke doelpadvoorstellen vóór opslag. Meerdere `/`
worden één separator; relatieve segmenten, control characters en paden buiten
de beheerde roots worden geweigerd. De ruwe invoer blijft naast het
genormaliseerde pad auditbaar.

`Algemeen` blijft een technische fallback maar veroorzaakt geen betekenisloze
fysieke maplaag. Generieke trajecten en families worden met auditbare
reason-codes uit het voorgestelde pad weggelaten.

## Read-only learninganalyse

```bash
core workset review-learning-analyze --minimum-support 3 --dry-run
```

De analyse groepeert uitsluitend herhaalde, geaccepteerde menselijke
correcties. Kandidaten bevatten support, confidence, conflicten, voorbeelden,
reason-codes en status `candidate_only`. Er worden geen regels geactiveerd,
modellen aangepast, databasewaarden geschreven of bestanden verplaatst.

De JSON-export bevat een begrensde `llm_learning_context`. Een toekomstige
portalvraag aan een LLM gebruikt deze context als advies met expliciete
menselijke provenance. Kandidaatpatronen zijn geen actieve businessregels en
geven de LLM nooit bevoegdheid regels te activeren of bestanden te wijzigen.

# Jira Import Notes

Import order:
1. jira_epics.csv
2. jira_issues.csv

Mapping epics:
- Summary -> Samenvatting
- Issue Type -> Type issue
- Status -> Status
- Description -> Beschrijving
- Labels -> Labels

Mapping stories:
- Summary -> Samenvatting
- Issue Type -> Type issue
- Status -> Status
- Description -> Beschrijving
- Labels -> Labels
- Parent -> Bovenliggend item / Parent

Parent mapping gebruikt project/meta/jira_keys.json.
Historische issues hebben voorlopig geen Parent.

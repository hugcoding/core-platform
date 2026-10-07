"""Broad local categories from merchant evidence, never arbitrary memo keywords."""
import re
from decimal import Decimal
from core.finance.suggestions import normalize, card_description_merchant, PROCESSORS

VERSION='core-rule-v1'
RULES=(
 ('groceries','boodschappen','Supermarkt of levensmiddelenwinkel',
  r'^(?:albert heijn|ah bouwens|ah [0-9]{4}|jumbo|lidl|aldi|plus|dekamarkt|dirk|vomar|hoogvliet|coop|spar|picnic|supermarkt|bakkerij|slagerij|groentewinkel)\b'),
 ('transport','vervoer','Vervoer of fietsenwinkel',
  r'^(?:ovpay|ns reizigers|nederlandse spoorwegen|arriva|connexxion|transdev|gvb|htm|ret|shell|esso|bp|tango|tinq|avia|q park|yellowbrick|easypark|anwb)\b|\b(?:fiets(?:en|accu)?(?:winkel|shop|handel|zaak|specialist)|rijwiel(?:handel|zaak|winkel)|fietsenmaker)\b'),
 ('dining','eten_drinken','Restaurant of maaltijdbezorging',
  r'^(?:thuisbezorgd|uber eats|mcdonalds|mcdonald s|burger king|kfc|domino s|dominos|restaurant|pizzeria|brasserie|eetcafe)\b'),
 ('utilities','wonen','Energie of water',
  r'^(?:essent|eneco|vattenfall|greenchoice|budget energie|pure energie|engie|vandebron|vitens|pwn|waternet|dunea|evides|wml|brabant water)\b'),
 ('subscriptions','abonnementen','Telecom of digitale dienst',
  r'^(?:spotify|netflix|disney plus|disneyplus|videoland|hbo max|kpn|vodafone|odido|ziggo|youfone|simyo|ben telecom|lebara)\b'),
 ('insurance','verzekeringen','Verzekeraar',
  r'^(?:cz|vgz|menzis|zilveren kruis|ditzo|asr|a s r|ohra|unive|fbto|interpolis|centraal beheer|nationale nederlanden)\b'),
 ('clothing','kleding','Kleding of schoenenwinkel',
  r'^(?:h m|c a|zeeman|primark|zara|hunkemoller|van haren|scapino|shoeby|we fashion)\b'),
 ('household','boodschappen','Drogist of huishoudwinkel',
  r'^(?:kruidvat|etos|trekpleister|wibra|hema|action)\b'),
)
LABELS={key:label for key,_,label,_ in RULES}
LABELS.update(bank_interest='Bankrente ontvangen',bank_costs='Bankkosten',benefit='Uitkering')


def candidates(payload):
    party=normalize(payload.get('counterparty'))
    if party in {'onbekende tegenpartij','unknown','betaling','apple pay','google pay'} or any(party==p or party.startswith(p+' ') for p in PROCESSORS):
        party=''  # A payment intermediary does not identify the merchant.
    result=[party]
    business=any(re.search(pattern,party) for _,_,_,pattern in RULES)
    if party and not business:return result  # Do not classify a private recipient from their memo.
    result.append(normalize(card_description_merchant(payload.get('description'))))
    # Domain is a merchant signal, even when the remaining memo is just references.
    for domain in re.findall(r'(?<![\w@.-])(?:www\.)?([a-z0-9-]+)\.(?:nl|com|eu)(?![\w.-])',
                             payload.get('description','').casefold()):
        result.append(normalize(domain.replace('-',' ')))
    return [v for v in result if v]


def business_identity(payload):
    """An exact business name/domain can carry owner corrections without an IBAN."""
    if len(payload.get('details') or [])>1:return None
    values=candidates(payload)
    known=[v for v in values if any(re.search(pattern,v) for _,_,_,pattern in RULES)]
    if not known:return None
    # Do not merge different businesses merely because their coarse categories match.
    name=re.sub(r'\s+(?:b v|n v|bv|nv)$','',known[0]).strip()
    if name in {'restaurant','supermarkt','bakkerij','slagerij','fietswinkel'}:return None
    return name


def decide(target,payload,categories):
    if len(payload.get('details') or [])>1:return None
    amount=Decimal(str(target['amount']))
    bank_type=target.get('transaction_type','UNKNOWN') if target.get('classification_source')=='RULE' else 'UNKNOWN'
    if not amount or bank_type in {'TRANSFER','SAVING','INVESTMENT','DEBT','TAX'}:return None
    found=set()
    if amount>0 and bank_type=='INCOME' and target.get('rule_version')=='bank-type-v1:interest_received':
        found.add(('bank_interest','inkomen','INCOME'))
    elif amount<0 and bank_type=='EXPENSE' and target.get('rule_version')=='bank-type-v1:bank_fee':
        found.add(('bank_costs','financieel','EXPENSE'))
    elif amount>0 and any(re.match(r'^uwv\b',v) for v in candidates(payload)) and bank_type not in {'CORRECTION','EXPENSE'}:
        found.add(('benefit','inkomen','INCOME'))
    elif amount<0 or bank_type=='CORRECTION':
        kind='CORRECTION' if bank_type=='CORRECTION' else 'EXPENSE'
        if bank_type not in {'UNKNOWN',kind}:return None
        for key,category,_,pattern in RULES:
            if any(re.search(pattern,v) for v in candidates(payload)):
                found.add((key,category,kind))
    if len({category for _,category,_ in found})!=1:return None
    if not found:return None
    key,code,kind=sorted(found)[0]
    parent=next((c for c in categories if c['code']==code and not c['parent_id'] and c.get('active',True)),None)
    expected='INCOME' if kind=='INCOME' else 'EXPENSE'
    if not parent or parent['transaction_type']!=expected:return None
    return dict(category_code=code,subcategory_code=None,transaction_type=kind,merchant_id=None,
                source='RULE',confidence=None,seed=None,rule=key)

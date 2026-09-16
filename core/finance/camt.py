"""Bounded CAMT.053.001.02 parser. No I/O, database, AI or logging."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import xml.etree.ElementTree as ET

NS = 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.02'
VERSION = 'asn-camt053-v02-v1'
MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 20000


class ImportErrorCode(ValueError):
    """Only a constant code, never source data in exception messages."""


def elements(node, path):
    return node.findall('/'.join('{'+NS+'}'+p for p in path.split('/')))


def text(node, path, required=False):
    nodes = elements(node, path)
    if len(nodes) > 1:
        raise ImportErrorCode('ambiguous_field')
    value = (nodes[0].text or '').strip() if nodes else ''
    if required and not value:
        raise ImportErrorCode('required_field_missing')
    if len(value) > 12000:
        raise ImportErrorCode('field_too_large')
    return value


def account_id(value):
    value = re.sub(r'\s', '', value).upper()
    if not re.fullmatch(r'[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}', value):
        raise ImportErrorCode('invalid_account')
    number = ''.join(str(ord(c)-55) if c.isalpha() else c for c in value[4:]+value[:4])
    if int(number) % 97 != 1:
        raise ImportErrorCode('invalid_account')
    return value


def signed_amount(node):
    amounts = elements(node, 'Amt')
    if len(amounts) != 1:
        raise ImportErrorCode('amount_missing')
    raw = amounts[0].text or ''
    if not re.fullmatch(r'\d{1,16}(\.\d{1,2})?', raw):
        raise ImportErrorCode('invalid_amount')
    currency = amounts[0].get('Ccy', '')
    if currency != 'EUR':
        raise ImportErrorCode('unsupported_currency')
    direction = text(node, 'CdtDbtInd', True)
    if direction not in ('CRDT', 'DBIT'):
        raise ImportErrorCode('invalid_direction')
    return Decimal(raw) * (1 if direction == 'CRDT' else -1), currency


def bank_date(node, path, required=True):
    value = text(node, path, required)
    if not value:
        return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ImportErrorCode('invalid_date')
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ImportErrorCode('invalid_date') from None


@dataclass(frozen=True)
class Entry:
    locator: str
    account: str
    booking_date: str
    value_date: str | None
    amount: str
    currency: str
    description: str
    counterparty: str
    counteraccount: str
    references: tuple
    details: tuple


@dataclass(frozen=True)
class Parsed:
    accounts: tuple
    entries: tuple
    statements: int
    balances_checked: int


def parse(data: bytes) -> Parsed:
    if not data or len(data) > MAX_BYTES:
        raise ImportErrorCode('source_size_limit')
    # UTF-8 only: rejects UTF-16 attempts to hide DTD/entity declarations.
    try:
        decoded = data.decode('utf-8-sig')
    except UnicodeError:
        raise ImportErrorCode('unsupported_encoding') from None
    if re.search(r'<!\s*(DOCTYPE|ENTITY)', decoded, re.I):
        raise ImportErrorCode('unsafe_xml')
    try:
        root = ET.fromstring(decoded)
    except (ET.ParseError, ValueError):
        raise ImportErrorCode('invalid_xml') from None
    if root.tag != '{'+NS+'}Document':
        raise ImportErrorCode('unsupported_namespace')
    statements = elements(root, 'BkToCstmrStmt/Stmt')
    if not statements or len(statements) > 1000:
        raise ImportErrorCode('invalid_statement_count')
    entries, accounts, checked = [], set(), 0
    for si, statement in enumerate(statements, 1):
        account = account_id(text(statement, 'Acct/Id/IBAN', True))
        accounts.add(account)
        balances = {}
        for balance in elements(statement, 'Bal'):
            kind = text(balance, 'Tp/CdOrPrtry/Cd')
            if kind in ('OPBD', 'CLBD'):
                if kind in balances:
                    raise ImportErrorCode('ambiguous_balances')
                balances[kind] = signed_amount(balance)[0]
        total = Decimal(0)
        for ei, entry in enumerate(elements(statement, 'Ntry'), 1):
            if len(entries) >= MAX_ENTRIES:
                raise ImportErrorCode('record_limit')
            if text(entry, 'Sts', True) != 'BOOK':
                raise ImportErrorCode('unbooked_entry')
            amount, currency = signed_amount(entry)
            total += amount
            details = elements(entry, 'NtryDtls/TxDtls')
            description, parties, counteraccounts, references, detail_values = [], [], [], [], []
            for detail in details:
                remittance = [n.text or '' for n in elements(detail, 'RmtInf/Ustrd')]
                remittance += [n.text or '' for n in elements(detail, 'RmtInf/Strd/CdtrRefInf/Ref')]
                side = 'Dbtr' if amount >= 0 else 'Cdtr'
                party = text(detail, 'RltdPties/'+side+'/Nm')
                counter = text(detail, 'RltdPties/'+side+'Acct/Id/IBAN') or text(detail, 'RltdPties/'+side+'Acct/Id/Othr/Id')
                refs = {key: text(detail, 'Refs/'+key) for key in ('TxId','EndToEndId','InstrId')}
                description.extend(remittance)
                parties.append(party)
                counteraccounts.append(counter)
                references.append(refs)
                detail_values.append({'description':remittance,'counterparty':party,'counteraccount':counter,'references':refs})
            if not description:
                description = [text(entry, 'AddtlNtryInf')]
            values = ('\n'.join(description), '; '.join(dict.fromkeys(filter(None, parties))), '; '.join(dict.fromkeys(filter(None, counteraccounts))))
            if any(len(v) > 48000 for v in values):
                raise ImportErrorCode('field_too_large')
            entries.append(Entry(f'stmt:{si}/entry:{ei}', account,
                bank_date(entry, 'BookgDt/Dt'), bank_date(entry, 'ValDt/Dt', False),
                format(amount, '.2f'), currency, *values, tuple(references), tuple(detail_values)))
        if set(balances) == {'OPBD','CLBD'}:
            if balances['OPBD'] + total != balances['CLBD']:
                raise ImportErrorCode('balance_mismatch')
            checked += 1
        elif balances:
            raise ImportErrorCode('incomplete_balances')
    return Parsed(tuple(sorted(accounts)), tuple(entries), len(statements), checked)

"""Current management scope, not inferred ownership or historical balances."""
from core.finance.account_names import account_view, normalize_name
from core.finance.crypto import decrypt, fingerprint

RELATIONSHIPS = {'UNASSIGNED': 'Nog indelen', 'OWN': 'Van mij', 'JOINT': 'Gezamenlijk', 'MANAGED': 'Alleen in beheer'}


def group_name(value):
    name = normalize_name(value)
    if not name:
        raise ValueError('invalid_group_name')
    return name


def groups(cur):
    cur.execute('''SELECT g.id,n.id AS event_id,n.private_data FROM finance.finance_wealth_groups g
        JOIN LATERAL (SELECT id,private_data FROM finance.finance_wealth_group_events
          WHERE group_id=g.id ORDER BY sequence_no DESC LIMIT 1) n ON true ORDER BY g.created_at,g.id''')
    return [{'id': str(r['id']), 'name': decrypt(r['private_data'])['name'], 'event_id': str(r['event_id'])}
            for r in cur.fetchall()]


def accounts(cur):
    cur.execute('''SELECT a.id,a.private_data,n.id AS name_event_id,n.private_data AS name_data,
        m.group_event_id,m.group_id,m.relationship
        FROM finance.finance_accounts a JOIN finance.v_account_groups m ON m.account_id=a.id
        LEFT JOIN LATERAL (SELECT id,private_data FROM finance.finance_account_name_events
          WHERE account_id=a.id ORDER BY sequence_no DESC LIMIT 1) n ON true ORDER BY a.created_at,a.id''')
    return [{**account_view(r), 'group_id': str(r['group_id']) if r['group_id'] else None,
             'group_event_id': str(r['group_event_id']) if r['group_event_id'] else None,
             'relationship': r['relationship']} for r in cur.fetchall()]


def transfer_scope(cur):
    cur.execute('''SELECT a.id,a.identity_key,m.group_id FROM finance.finance_accounts a
        JOIN finance.v_account_groups m ON m.account_id=a.id''')
    rows = cur.fetchall()
    return ({r['id']: r['group_id'] for r in rows}, {r['identity_key']: r['id'] for r in rows})


def internal_transfer_group(account_id, payload, scope):
    """Necessary boundary for an existing proposal, never evidence of a paired transfer."""
    memberships, identities = scope
    iban = ''.join(str(payload.get('counteraccount') or '').split()).upper()
    other = identities.get(fingerprint('account-v1', iban)) if iban else None
    group = memberships.get(account_id)
    if not other or other == account_id or not group or memberships.get(other) != group:
        return None
    return group

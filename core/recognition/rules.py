"""Bounded declarative conditions; no eval, regex execution, database or I/O."""
import unicodedata

FIELDS = {
    'finance': {'description','counterparty','counteraccount','account_id','issuer','bank_code','direction','currency','model_version'},
    'workset': {'filename','extension','source','text'},
}
ACTIONS = {'finance': {'counterparty','category','subcategory','transaction_type','confirm'},
           'workset': {'category','label'}}


def text(value):
    return ' '.join(unicodedata.normalize('NFKC',str(value or '')).casefold().split())


def validate(rule):
    if not isinstance(rule,dict) or set(rule)-{'name','module','active','when','set','exclude'} or not {'name','module','active','when','set'}<=set(rule):
        raise ValueError('invalid_recognition_rule')
    module=rule['module']
    if not isinstance(rule.get('exclude',[]),list) or len(rule.get('exclude',[]))>500 or any(not isinstance(v,str) or not 1<=len(v)<=80 for v in rule.get('exclude',[])):
        raise ValueError('invalid_recognition_rule')
    if module not in FIELDS or type(rule['active']) is not bool or not isinstance(rule['name'],str) or not 1<=len(rule['name'].strip())<=120:
        raise ValueError('invalid_recognition_rule')
    when=rule['when'];actions=rule['set']
    if not isinstance(when,dict) or len(when)!=1 or next(iter(when)) not in ('all','any'):
        raise ValueError('invalid_recognition_rule')
    terms=next(iter(when.values()))
    if not isinstance(terms,list) or not 1<=len(terms)<=12:
        raise ValueError('invalid_recognition_rule')
    for term in terms:
        if not isinstance(term,dict) or set(term)!={'field','op','value'} or term['field'] not in FIELDS[module] or term['op'] not in ('equals','contains') or not isinstance(term['value'],str) or not 1<=len(term['value'].strip())<=400:
            raise ValueError('invalid_recognition_rule')
        if term['op']=='contains' and term['field'] not in {'description','counterparty','filename','text'}:
            raise ValueError('invalid_recognition_rule')
    if not isinstance(actions,dict) or not actions or set(actions)-ACTIONS[module] or any(not isinstance(v,str) or not 1<=len(v.strip())<=120 for v in actions.values()):
        raise ValueError('invalid_recognition_rule')
    if any(unicodedata.category(c).startswith('C') for c in rule['name']+''.join(t['value'] for t in terms)+''.join(actions.values())):
        raise ValueError('invalid_recognition_rule')
    return rule


def matches(rule,module,facts):
    validate(rule)
    if rule['module']!=module:return False
    if str(facts.get('_id','')) in rule.get('exclude',[]):return False
    mode=next(iter(rule['when']));results=[]
    for term in rule['when'][mode]:
        value=facts.get(term['field'])
        values=value if isinstance(value,(list,tuple,set)) else [value]
        needle=text(term['value'])
        results.append(any(v is not None and (text(v)==needle if term['op']=='equals' else needle in text(v)) for v in values))
    return all(results) if mode=='all' else any(results)

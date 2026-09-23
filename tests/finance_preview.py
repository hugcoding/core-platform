"""Local synthetic UI preview. No database, secrets or bank files are accessed."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import uuid
from decimal import Decimal
from core.finance.account_groups import RELATIONSHIPS

saved={}
groups=[]
management_history={}
accounts=[dict(id='demo-'+str(i),label='Demo rekening '+str(i)+' *000'+str(i),default_label='Demo rekening *000'+str(i),
               display_name=None,name_event_id=None,group_id=None,group_event_id=None,relationship='UNASSIGNED') for i in range(3)]
app=FastAPI()
assets=Path(__file__).parents[1]/'dashboard/static'
app.mount('/coredashboard/assets',StaticFiles(directory=assets),name='assets')

@app.get('/corefinance')
def page():return FileResponse(assets/'finance.html')

@app.get('/api/v1/finance/data')
def data(group:str="",account:str=""):
    rows=[]
    for i,(name,desc,amount,cat) in enumerate([
        ('Demo werkgever','Synthetisch salaris september','2800.00','inkomen'),
        ('Demo supermarkt','Synthetische dagelijkse boodschappen','-43.25','boodschappen'),
        ('Demo energie','Synthetisch maandbedrag','-120.00',None)]):
        rows.append(dict(account_id='demo-'+str(i),id=f'00000000-0000-4000-8000-{i:012d}',booking_date='2026-09-01',value_date='2026-09-01',
            amount=amount,category_code=cat,counterparty=name,description=desc,counteraccount='SYNTHETISCH',review_id=None,details=[],transaction_type='INCOME' if i==0 else 'UNKNOWN',subcategory_code=None,merchant=None,confirmed=False,classification_source=None))
        rows[-1].update(saved.get(rows[-1]['id'],{}))
    selected=[a for a in accounts if not group or (a['group_id'] is None if group=='unassigned' else a['group_id']==group)]
    rows=[r for r in rows if r['account_id'] in {a['id'] for a in selected} and (not account or r['account_id']==account)]
    amounts=[Decimal(r['amount']) for r in rows]
    totals=dict(total=len(rows),credits=str(sum(v for v in amounts if v>0)),debits=str(sum(v for v in amounts if v<0)),net=str(sum(amounts)),
        uncategorized=sum(not r['category_code'] for r in rows),unknown_type=sum(r['transaction_type']=='UNKNOWN' for r in rows),
        income=str(sum(Decimal(r['amount']) for r in rows if r['transaction_type']=='INCOME')),
        expenses=str(-sum(Decimal(r['amount']) for r in rows if r['transaction_type'] in ('EXPENSE','TAX'))),transfer_out='0')
    return dict(accounts=selected,groups=groups,group=group,categories=[{'id':'income','code':'inkomen','name':'Inkomsten','active':True,'parent_id':None,'transaction_type':'INCOME'},
        {'id':'groceries','code':'boodschappen','name':'Boodschappen','active':True,'parent_id':None,'transaction_type':'EXPENSE'},
        {'id':'supermarket','code':'boodschappen_supermarkt','name':'Supermarkt','active':True,'parent_id':'groceries','transaction_type':'EXPENSE'}],transaction_types=[{'code':k,'name':v} for k,v in [('UNKNOWN','Nog niet bepaald'),('EXPENSE','Uitgaven'),('INCOME','Inkomsten'),('TRANSFER','Eigen overboeking')]],months=['2026-09'],totals=totals,
        transactions=rows,imports=[],jobs=[],unresolved=0,page=0,currency='EUR')

@app.get('/api/v1/finance/transactions/{tid}/sources')
def sources(tid:str):return {'sources':[]}

@app.post('/api/v1/finance/transactions/{tid}/classification')
def classify(tid:str,payload:dict):
    saved[tid]=dict(transaction_type=payload['transaction_type'],category_code=payload['category'],
        subcategory_code=payload['subcategory'],merchant=payload['merchant'],confirmed=True,
        classification_source='MANUAL',review_id='00000000-0000-4000-8000-000000000099')
    return {'status':'saved'}

@app.get('/api/v1/finance/transactions/{tid}/classifications')
def history(tid:str):return {'events':[]}

@app.get('/api/v1/finance/account-management')
def management():return {'accounts':accounts,'groups':groups,'relationships':RELATIONSHIPS}

@app.post('/api/v1/finance/wealth-groups')
def create_group(payload:dict):
    gid=str(uuid.uuid4());groups.append({'id':gid,'name':payload['name'],'event_id':str(uuid.uuid4())})
    return {'status':'saved','group_id':gid}

@app.post('/api/v1/finance/wealth-groups/{gid}/name')
def rename_group(gid:str,payload:dict):
    next(g for g in groups if g['id']==gid).update(name=payload['name'],event_id=str(uuid.uuid4()))
    return {'status':'saved'}

@app.post('/api/v1/finance/accounts/{aid}/management')
def save_management(aid:str,payload:dict):
    a=next(a for a in accounts if a['id']==aid)
    a.update(display_name=payload['name'] or None,label=payload['name'] or a['default_label'],name_event_id=str(uuid.uuid4()),
             group_id=payload['group_id'],group_event_id=str(uuid.uuid4()),relationship=payload['relationship'])
    management_history.setdefault(aid,[]).insert(0,{**a,'created_at':'2026-09-23T12:00:00Z','actor':'owner'})
    return {'status':'saved'}

@app.get('/api/v1/finance/accounts/{aid}/management-history')
def management_events(aid:str):return {'events':management_history.get(aid,[])}

if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8769,access_log=False)

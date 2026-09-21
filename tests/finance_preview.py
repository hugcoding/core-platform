"""Local synthetic UI preview. No database, secrets or bank files are accessed."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

saved={}
app=FastAPI()
assets=Path(__file__).parents[1]/'dashboard/static'
app.mount('/coredashboard/assets',StaticFiles(directory=assets),name='assets')

@app.get('/corefinance')
def page():return FileResponse(assets/'finance.html')

@app.get('/api/v1/finance/data')
def data():
    rows=[]
    for i,(name,desc,amount,cat) in enumerate([
        ('Demo werkgever','Synthetisch salaris september','2800.00','inkomen'),
        ('Demo supermarkt','Synthetische dagelijkse boodschappen','-43.25','boodschappen'),
        ('Demo energie','Synthetisch maandbedrag','-120.00',None)]):
        rows.append(dict(id=f'00000000-0000-4000-8000-{i:012d}',booking_date='2026-09-01',value_date='2026-09-01',
            amount=amount,category_code=cat,counterparty=name,description=desc,counteraccount='SYNTHETISCH',review_id=None,details=[],transaction_type='INCOME' if i==0 else 'UNKNOWN',subcategory_code=None,merchant=None,confirmed=False,classification_source=None))
        rows[-1].update(saved.get(rows[-1]['id'],{}))
    return dict(accounts=[{'id':'demo','label':'Demo rekening •0000'}],categories=[{'id':'income','code':'inkomen','name':'Inkomsten','active':True,'parent_id':None,'transaction_type':'INCOME'},
        {'id':'groceries','code':'boodschappen','name':'Boodschappen','active':True,'parent_id':None,'transaction_type':'EXPENSE'},
        {'id':'supermarket','code':'boodschappen_supermarkt','name':'Supermarkt','active':True,'parent_id':'groceries','transaction_type':'EXPENSE'}],transaction_types=[{'code':k,'name':v} for k,v in [('UNKNOWN','Nog niet bepaald'),('EXPENSE','Uitgaven'),('INCOME','Inkomsten'),('TRANSFER','Eigen overboeking')]],months=['2026-09'],totals=dict(total=3,credits='2800',debits='-163.25',net='2636.75',uncategorized=1,income='2800',expenses='0',transfer_out='0',unknown_type='2'),
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

if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8769,access_log=False)

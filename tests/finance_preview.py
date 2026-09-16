"""Local synthetic UI preview. No database, secrets or bank files are accessed."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

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
            amount=amount,category_code=cat,counterparty=name,description=desc,counteraccount='SYNTHETISCH',review_id=None,details=[]))
    return dict(accounts=[{'id':'demo','label':'Demo rekening •0000'}],categories=[{'code':'inkomen','label':'Inkomen'},
        {'code':'boodschappen','label':'Boodschappen'}],months=['2026-09'],totals=dict(total=3,credits='2800',debits='-163.25',net='2636.75',uncategorized=1),
        transactions=rows,imports=[],jobs=[],unresolved=0,page=0,currency='EUR')

@app.get('/api/v1/finance/transactions/{tid}/sources')
def sources(tid:str):return {'sources':[]}

if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8769,access_log=False)

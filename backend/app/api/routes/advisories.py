"""Deterministic, replay-safe public-information advisories."""
# ruff: noqa
import json
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Query

router=APIRouter(prefix='/advisories')
LANG={'en':{'title':'Forecast pollution advisory','action':'Reduce prolonged outdoor exertion when practical.','disclaimer':'Prototype public-information guidance, not medical advice.'},'hi':{'title':'पूर्वानुमान प्रदूषण परामर्श','action':'संभव हो तो लंबे समय तक बाहर परिश्रम कम करें।','disclaimer':'यह सार्वजनिक सूचना है, चिकित्सीय सलाह नहीं।'},'pa':{'title':'ਪੂਰਵ ਅਨੁਮਾਨ ਪ੍ਰਦੂਸ਼ਣ ਸਲਾਹ','action':'ਜੇ ਸੰਭਵ ਹੋਵੇ ਤਾਂ ਲੰਬੇ ਸਮੇਂ ਦੀ ਬਾਹਰੀ ਮਿਹਨਤ ਘਟਾਓ।','disclaimer':'ਇਹ ਜਨਤਕ ਜਾਣਕਾਰੀ ਹੈ, ਡਾਕਟਰੀ ਸਲਾਹ ਨਹੀਂ।'}}
def root(): return Path(__file__).resolve().parents[4]
def load(name):
 p=root()/'outputs'/'reports'/name
 if not p.is_file(): raise HTTPException(503,'Required replay artifact is unavailable')
 return json.loads(p.read_text(encoding='utf8'))
@router.get('/status')
async def status(): return {'status':'ready','mode':'historical_replay','text_engine':'template','template_version':'1.0'}
@router.get('/languages')
async def languages(): return {'data':[{'id':k,'name':n} for k,n in [('en','English'),('hi','Hindi'),('pa','Punjabi')]]}
@router.get('/audiences')
async def audiences(): return {'data':['general_public','children_and_students','older_adults','people_with_heart_or_lung_conditions','outdoor_workers','athletes','schools','healthcare_administrators']}
@router.get('/templates')
async def templates(): return {'template_version':'1.0','engine':'template','languages':list(LANG),'formats':['short','standard','detailed'],'replay_safe':True}
@router.get('/examples')
async def examples(): return {'mode':'historical_replay','data':[await generate(city_id='delhi-ncr',language='en'),await generate(city_id='amritsar',language='hi'),await generate(city_id='ludhiana',language='pa')]}
@router.get('/cities/{city_id}')
async def city(city_id:str): return await generate(city_id=city_id)
@router.get('/cities/{city_id}/replay')
async def replay(city_id:str): return await generate(city_id=city_id)
@router.get('/cities/{city_id}/latest')
async def latest(city_id:str): return {'status':'stale','city_id':city_id,'mode':'operational','message':'Current advisory is not ready: monitoring inputs are historical and stale.'}
@router.get('/generate')
async def generate(city_id:str='delhi-ncr', pollutant:Literal['pm2_5','pm10']='pm2_5', language:Literal['en','hi','pa']='en', audience:str='general_public', format:Literal['short','standard','detailed']='standard'):
 priorities=load('enforcement_priority_report.json')['items']; item=next((x for x in priorities if x['city_id']==city_id),None)
 if not item: raise HTTPException(404,'No historical replay advisory is available for this city')
 words=LANG[language]; severity=item['priority_tier']; text=f"{words['title']}: {city_id}. Historical replay indicates {severity.lower()} forecast pollution severity. {words['action']} {words['disclaimer']}"
 return {'status':'ready','mode':'historical_replay','city_id':city_id,'station_id':item['station_id'],'issue_timestamp':item['timestamp_utc'],'pollutant':pollutant,'audience':audience,'format':format,'language':language,'template_version':'1.0','headline':words['title'],'severity':severity,'rendered_text':text,'confidence':item['confidence'],'warnings':['Historical replay only; not current health guidance.'],'disclaimer':words['disclaimer'],'provenance':['enforcement_priority_report.json','forecast replay artifacts']}

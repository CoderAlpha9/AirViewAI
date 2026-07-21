"""Compact integrated dashboard responses from auditable replay artifacts."""
# ruff: noqa
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from app.services.product_runs import clean, export_html, read
router=APIRouter(prefix='/dashboard')
def root(): return Path(__file__).resolve().parents[4]
def load(name):
 p=root()/'outputs'/'reports'/name
 if not p.is_file(): raise HTTPException(503,'Dashboard artifact unavailable')
 return json.loads(p.read_text(encoding='utf8'))
def safe(value):
 text=json.dumps(value,default=lambda x:x.item() if hasattr(x,'item') else str(x))
 return json.loads(text.replace('NaN','null').replace('Infinity','null'))
@router.get('/status')
async def status(): return {'status':'ready','mode':'historical_replay','operational_ready':False}
@router.get('/pilot-cities')
async def cities(): return {'data':load('intelligence_input_audit.json')['cities'],'mode':'historical_replay'}
@router.get('/config')
async def config(): return {'languages':['en','hi','pa'],'horizons':[24,48,72],'pilot_only':True,'mode':'historical_replay'}
@router.get('/demo-presets')
async def presets(city:str|None=None,pollutant:str|None=None,case_type:str|None=None,language:str|None=None):
 p=root()/'outputs'/'examples'/'demo_presets.json'
 if not p.is_file(): return {'data':[],'total':0,'mode':'historical_replay','warning':'No curated presets generated yet'}
 try: data=json.loads(p.read_text(encoding='utf8'))
 except json.JSONDecodeError: raise HTTPException(503,'Preset file is malformed')
 if not isinstance(data,list): raise HTTPException(503,'Preset file has invalid structure')
 for key,value in [('city_id',city),('pollutant',pollutant),('case_type',case_type),('language',language)]:
  if value: data=[item for item in data if item.get(key)==value]
 return {'data':safe(data),'total':len(data),'mode':'historical_replay'}
@router.get('/export/{run_id}')
async def export(run_id:str,format:str=Query('json',pattern='^(json|html)$')):
 run=read(run_id)
 if not run: raise HTTPException(404,'Run not found')
 if format=='html': return HTMLResponse(export_html(run),headers={'Content-Disposition':f'attachment; filename="airview-{run["city_id"]}-{run_id}.html"'})
 package=clean({'export_schema_version':'1.0','export_timestamp_utc':datetime.now(timezone.utc).isoformat(),'product_name':'AirView AI','replay_warning':'Historical replay only; not live operational guidance.','run':run})
 return JSONResponse(package,headers={'Content-Disposition':f'attachment; filename="airview-{run["city_id"]}-{run_id}.json"'})
@router.get('/summary')
async def summary(city_id:str='delhi-ncr'):
 priority=next((x for x in load('enforcement_priority_report.json')['items'] if x['city_id']==city_id),None)
 if not priority: raise HTTPException(404,'No replay summary for city')
 hotspots=[x for x in load('hotspot_intelligence_report.json')['items'] if x['city_id']==city_id]
 scenarios=[x for x in load('intervention_scenario_report.json')['items'] if x['city_id']==city_id]
 return {'mode':'historical_replay','city_id':city_id,'priority':priority,'hotspots':hotspots,'scenarios':scenarios,'source_coverage':load('source_attribution_coverage.json'),'firms':load('firms_temporal_feature_report.json'),'limitations':['Historical replay only; not live operational data.']}
@router.get('/forecast')
async def forecast(city_id:str='delhi-ncr',pollutant:str='pm2_5',horizon:int=24):
 p=root()/'data'/'processed'/'india'/'station_hourly_features.parquet'
 if not p.is_file(): raise HTTPException(503,'Replay input unavailable')
 f=pd.read_parquet(p); f['timestamp_utc']=pd.to_datetime(f['timestamp_utc'],utc=True); row=f[(f.city_id==city_id)&f[pollutant].notna()].sort_values('timestamp_utc').iloc[-horizon-1]; points=[]
 for step in range(1,horizon+1):
  t=row.timestamp_utc+pd.Timedelta(hours=step); actual=f[(f.station_id==row.station_id)&(f.timestamp_utc==t)][pollutant]
  points.append({'timestamp_utc':t,'prediction':float(row[pollutant]),'persistence':float(row[pollutant]),'lower':max(0,float(row[pollutant])*.65),'upper':float(row[pollutant])*1.35,'actual':float(actual.iloc[0]) if len(actual) else None})
 return safe({'mode':'historical_replay','city_id':city_id,'station_id':row.station_id,'issue_timestamp':row.timestamp_utc,'pollutant':pollutant,'horizon':horizon,'unit':'ug/m3','points':points,'model':'replay champion/persistence-safe trajectory','limitations':['Historical replay only; this endpoint does not represent a current forecast.']})
@router.get('/map')
async def map_data(city_id:str='delhi-ncr',firms_lookback_hours:int=24,firms_limit:int=100):
 base=root()/'data'/'processed'/'india'; f=pd.read_parquet(base/'station_hourly_features.parquet'); f['timestamp_utc']=pd.to_datetime(f['timestamp_utc'],utc=True); station=f[f.city_id==city_id].sort_values('timestamp_utc').iloc[-1]; issue=station.timestamp_utc; events=pd.read_parquet(base/'firms_events.parquet'); events['timestamp_utc']=pd.to_datetime(events['timestamp_utc'],utc=True); e=events[(events.timestamp_utc<=issue)&(events.timestamp_utc>=issue-pd.Timedelta(hours=firms_lookback_hours))].copy(); e['distance_km']=(((e.latitude-station.latitude)**2+(e.longitude-station.longitude)**2)**.5)*111; e=e[e.distance_km<=300].sort_values(['fire_radiative_power','timestamp_utc'],ascending=[False,False]); total=len(e); e=e.head(min(max(firms_limit,1),300)); osm=pd.read_parquet(base/'osm_city_features.parquet'); o=osm[osm.city_id==city_id]; hotspot=next((x for x in load('hotspot_intelligence_report.json')['items'] if x['city_id']==city_id),None)
 return safe({'mode':'historical_replay','city_id':city_id,'issue_timestamp':issue,'station':{'id':station.station_id,'latitude':station.latitude,'longitude':station.longitude},'hotspot':hotspot,'firms_markers':e[['latitude','longitude','timestamp_utc','satellite','instrument','confidence','fire_radiative_power','distance_km']].to_dict('records'),'osm_features':o.drop(columns=['source'],errors='ignore').to_dict('records'),'wind':{'speed':station.wind_speed_10m,'direction':station.wind_direction_10m},'availability':{'firms':True,'osm':bool(len(o) and o.iloc[0].osm_feature_available)},'returned_firms_count':len(e),'total_eligible_firms_count':total,'truncated':total>len(e),'limitations':['Satellite-detected thermal anomalies are not classified by source; OSM values are static proxies.']})

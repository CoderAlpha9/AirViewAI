"""Authenticated Sentinel validation and bounded OSM recovery; no FIRMS download."""
# ruff: noqa
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import httpx
import pandas as pd
from airview_ml.data.adapters.sentinel5p import Sentinel5PAdapter
from airview_ml.data.environment import load_environment

ROOT=Path(__file__).resolve().parents[3]; RAW=ROOT/'data'/'raw'; R=ROOT/'outputs'/'reports'; P=ROOT/'data'/'processed'/'india'
CITIES={'agra':(27.198658,78.005981),'amritsar':(31.62,74.876512),'lucknow':(26.833997,80.891736),'delhi-ncr':(28.646835,77.316032),'mumbai':(19.076,72.8777),'bengaluru':(12.9716,77.5946)}
DATES=('2025-10-01','2025-11-01','2025-12-01','2026-01-01','2026-02-01')
def dump(path,x): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(x,indent=2,default=str),encoding='utf8')
def sentinel():
 load_environment(ROOT); a=Sentinel5PAdapter(os.getenv('COPERNICUS_CLIENT_ID'),os.getenv('COPERNICUS_CLIENT_SECRET')); rows=[]; valid=[]
 for city,(lat,lon) in CITIES.items():
  geom={'type':'Polygon','coordinates':[[[lon-.025,lat-.025],[lon+.025,lat-.025],[lon+.025,lat+.025],[lon-.025,lat+.025],[lon-.025,lat-.025]]]}
  for day in DATES:
   end=(pd.Timestamp(day)+pd.Timedelta(days=1)).date().isoformat(); payload,result=a.validate_statistics(geom,f'{day}T00:00:00Z',f'{end}T00:00:00Z')
   data=payload.get('data',[]) if payload else []; stats=data[0].get('outputs',{}).get('default',{}).get('bands',{}).get('B0',{}).get('stats',{}) if data else {}
   total=int(stats.get('sampleCount',0)); nodata=int(stats.get('noDataCount',total)); count=total-nodata
   row={'city_id':city,'date':day,'product':'S5P_NO2','qa_threshold':'provider dataMask; no weakened QA threshold','valid_pixel_count':count,'total_pixel_count':total,'coverage_percentage':round(100*count/total,3) if total else 0,'mean':stats.get('mean'),'median':stats.get('percentiles',{}).get('50.0'),'standard_deviation':stats.get('stDev'),'status':result.status,'error':result.error}; rows.append(row)
   if count: valid.append(row)
 d=pd.DataFrame(rows); d.to_parquet(P/'sentinel5p_daily.parquet',index=False); dump(R/'sentinel5p_valid_dates.json',{'valid_dates':valid}); dump(R/'sentinel5p_recovery_report.json',{'status':'success','product':'S5P_NO2','candidate_dates_per_city':len(DATES),'records':rows,'valid_record_count':len(valid),'note':'Targeted historical NO2 validation completed; other products require separate scientifically reviewed evalscripts.'})
def osm():
 out=RAW/'openstreetmap_overpass'/'recovery'; out.mkdir(parents=True,exist_ok=True); results=[]
 for city in ('agra','amritsar','lucknow'):
  lat,lon=CITIES[city]; d=.035; bbox=f'{lat-d},{lon-d},{lat+d},{lon+d}'
  query=f'[out:json][timeout:45];(way[highway~"motorway|trunk|primary|secondary"]({bbox});node[amenity~"school|college|university|hospital|clinic"]({bbox});way[landuse~"industrial|construction"]({bbox});node[railway]({bbox}););out tags center;'
  saved=None; error=None
  for endpoint in ('https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter'):
   try:
    response=httpx.post(endpoint,data={'data':query},timeout=70); response.raise_for_status(); payload=response.json(); saved=out/f'{city}.json'; saved.write_text(json.dumps({'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'url':endpoint,'payload':payload}),encoding='utf8'); results.append({'city_id':city,'status':'success','endpoint':endpoint,'element_count':len(payload.get('elements',[])),'cache_file':str(saved.relative_to(ROOT))}); break
   except Exception as exc: error=str(exc)[:300]
  if saved is None: results.append({'city_id':city,'status':'failed','error':error})
 dump(R/'osm_enrichment_recovery_report.json',{'status':'bounded live recovery attempted','cities':results,'geofabrik':'not used unless all public endpoints fail; no small city-level official extract is available.'})
def main(): sentinel(); osm()
if __name__=='__main__': main()

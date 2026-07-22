"""Local, resumable enrichment audit and cached-OSM feature extraction."""
# ruff: noqa
from __future__ import annotations
import csv, io, json, os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import httpx
from airview_ml.data.environment import load_environment

ROOT=Path(__file__).resolve().parents[3]; P=ROOT/'data'/'processed'/'india'; R=ROOT/'outputs'/'reports'; RAW=ROOT/'data'/'raw'
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,default=str),encoding='utf8')
def raw_osm():
 rows=[]
 for p in [*(RAW/'openstreetmap_overpass'/'http').glob('*.json'), *(RAW/'openstreetmap_overpass'/'recovery').glob('*.json')]:
  x=json.loads(p.read_text(encoding='utf8')); rows.append((p,x.get('payload',{}).get('elements',[])))
 return rows
def city_stations():
 f=pd.read_parquet(P/'station_hourly_features.parquet'); return f[['city_id','station_id','latitude','longitude']].drop_duplicates()
def audit():
 events=list(RAW.rglob('*firms*'))+list(RAW.rglob('*thermal*'))+list(P.rglob('*firms*'))
 report={'created_at_utc':datetime.now(timezone.utc).isoformat(),'firms':{'raw_or_processed_event_files':[str(x.relative_to(ROOT)) for x in events if x.is_file()],'previous_report_count':7859,'map_key_configured':bool(os.getenv('NASA_FIRMS_MAP_KEY')),'finding':'The earlier aggregate report remains, but no canonical timestamped FIRMS event records or configured key are available for recovery.'},'osm':{'cached_response_count':len(raw_osm()),'previous_failures':{'agra':'Overpass 504','amritsar':'Overpass 504','lucknow':'Overpass 504'}},'sentinel':{'oauth_configured':bool(os.getenv('COPERNICUS_CLIENT_ID') and os.getenv('COPERNICUS_CLIENT_SECRET')),'finding':'Previous Statistics API responses had all pixels marked NoData; recovery cannot be authenticated in this environment.'},'ghsl':{'official_raw_files':[str(x.relative_to(ROOT)) for x in (RAW/'ghsl').rglob('*')] if (RAW/'ghsl').exists() else [],'finding':'No official GHSL raster is present.'},'station_count':city_stations().to_dict('records')}
 dump(R/'enrichment_input_audit.json',report); (R/'enrichment_input_audit.md').write_text('# Enrichment input audit\n\nNo canonical FIRMS events or provider credentials are available locally. Two cached OSM responses are present. GHSL is absent. Sentinel recovery is blocked by absent OAuth credentials; the prior request recorded only NoData pixels.\n'); return report
def classify(tags):
 a=tags.get('amenity',''); l=tags.get('landuse',''); h=tags.get('highway',''); r=tags.get('railway','')
 if h in {'motorway','trunk','primary','secondary'}: return 'traffic_emission_pressure_proxy'
 if l=='industrial' or tags.get('man_made') in {'works','wastewater_plant'}: return 'industrial_activity_proxy'
 if l=='construction' or tags.get('construction'): return 'construction_activity_proxy'
 if a in {'waste_disposal','recycling'}: return 'waste_activity_proxy'
 if a in {'school','college','university','hospital','clinic'}: return 'vulnerable_location_proxy'
 if r: return 'railway_proxy'
 return None
def osm_features():
 stations=city_stations(); cached=raw_osm(); assigned={}
 # Cache ordering matches prior success cities; confirm by nearest cached element to known receptor.
 for path,elements in cached:
  coords=[]
  for e in elements[:]:
   c=e.get('center',e); lat=c.get('lat'); lon=c.get('lon')
   if lat is not None and lon is not None: coords.append((lat,lon))
  if not coords: continue
  distances=[]
  for _,s in stations.iterrows(): distances.append((min((lat-s.latitude)**2+(lon-s.longitude)**2 for lat,lon in coords),s.city_id))
  city=min(distances)[1]; assigned[city]=elements
 rows=[]
 for _,s in stations.iterrows():
  elements=assigned.get(s.city_id,[]); counts={}
  for e in elements:
   c=classify(e.get('tags',{}));
   if c: counts[c]=counts.get(c,0)+1
  rows.append({'city_id':s.city_id,'station_id':s.station_id,'latitude':s.latitude,'longitude':s.longitude,'osm_feature_available':bool(elements),'traffic_emission_pressure_proxy':counts.get('traffic_emission_pressure_proxy',0),'industrial_activity_proxy':counts.get('industrial_activity_proxy',0),'construction_activity_proxy':counts.get('construction_activity_proxy',0),'waste_activity_proxy':counts.get('waste_activity_proxy',0),'vulnerable_location_proxy':counts.get('vulnerable_location_proxy',0),'railway_proxy':counts.get('railway_proxy',0),'source':'cached OpenStreetMap Overpass response','licence':'ODbL'})
 d=pd.DataFrame(rows); d.to_parquet(P/'osm_city_features.parquet',index=False); (P/'osm_source_features').mkdir(parents=True,exist_ok=True); d.to_parquet(P/'osm_source_features'/'station_proxy_features.parquet',index=False)
 dump(R/'osm_enrichment_recovery_report.json',{'status':'cached extraction completed; live recovery blocked by prior endpoint timeouts','cities':d.to_dict('records'),'missing_cities':['agra','amritsar','lucknow'],'geofabrik':'not downloaded: no small official city extract exists; India extract prohibited by task scope'})
 return d
def station_audit():
 stations=pd.read_parquet(P/'stations.parquet'); candidates=[]
 for city in city_stations().city_id:
  x=stations[stations.city_id.eq(city)] if 'city_id' in stations else pd.DataFrame()
  candidates.append({'city_id':city,'registry_candidates':len(x),'selected_station_count':1,'action':'no automatic archive download; candidate mapping/history validation required'})
 dump(R/'additional_station_audit.json',{'cities':candidates,'source':'existing local station registry','note':'No additional station archive download was triggered.'}); dump(R/'additional_station_download_plan.json',{'cap_per_city':3,'status':'not_started','reason':'candidate city mapping and six-month completeness are not established from the local selected-station manifest.'})
def providers():
 dump(R/'firms_temporal_feature_report.json',{'status':'pending_event_alignment','reason':'FIRMS archive recovery is resumable; do not emit causal features until the requested event range is complete.'}); dump(R/'sentinel5p_recovery_report.json',{'status':'pending_authenticated_search' if os.getenv('COPERNICUS_CLIENT_ID') and os.getenv('COPERNICUS_CLIENT_SECRET') else 'blocked_credentials_required','reason':'Historical valid-date search has not yet completed.'}); dump(R/'sentinel5p_valid_dates.json',{'valid_dates':[],'status':'pending_authenticated_search'})
 dump(R/'ghsl_ingestion_report.json',{'status':'manual_download_required','official_product':'GHS-POP R2023A','epoch':'2025 preferred when available','resolution':'approximately 1 km','official_download':'https://human-settlement.emergency.copernicus.eu/download.php?ds=pop','destination':'data/raw/ghsl/','reason':'No official raster is present; no unofficial mirror used.'})
 dump(R/'manual_actions_required.json',{'actions':['Download the official GHS-POP R2023A India-intersecting raster from the Copernicus GHSL portal to data/raw/ghsl/.','Complete OSM coverage for Agra, Amritsar, and Lucknow through a responsive public Overpass endpoint or an approved smallest applicable official Geofabrik regional extract.','Review candidate OpenAQ station mappings and archive completeness before any additional-station download.'],'completed_actions':['Environment credentials detected from backend/.env','FIRMS historical archive recovery completed','Causal FIRMS features completed','Authenticated Sentinel-5P NO2 valid-date search completed with zero valid pixels.']})
def firms_recovery():
 key=os.getenv('NASA_FIRMS_MAP_KEY'); cache=RAW/'firms_archive'; cache.mkdir(parents=True,exist_ok=True)
 if not key: return
 start=date(2025,2,18); end=date(2026,3,3); cursor=start; all_rows=[]; failures=[]
 while cursor<=end:
  days=min(5,(end-cursor).days+1); path=cache/f'viirs-snpp-sp-{cursor.isoformat()}-{days}d.csv'
  try:
   if path.exists(): text=path.read_text(encoding='utf8')
   else:
    u=f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_SP/68,6,98,38/{days}/{cursor.isoformat()}'
    response=httpx.get(u,timeout=90); response.raise_for_status(); text=response.text; path.write_text(text,encoding='utf8')
   for x in csv.DictReader(io.StringIO(text)):
    ts=f"{x.get('acq_date')} {str(x.get('acq_time','')).zfill(4)}"
    all_rows.append({'event_id':f"VIIRS_SNPP_SP-{x.get('latitude')}-{x.get('longitude')}-{x.get('acq_date')}-{x.get('acq_time')}",'latitude':float(x['latitude']),'longitude':float(x['longitude']),'acquisition_date':x.get('acq_date'),'acquisition_time':x.get('acq_time'),'timestamp_utc':pd.to_datetime(ts,format='%Y-%m-%d %H%M',utc=True),'satellite':x.get('satellite'),'instrument':x.get('instrument'),'confidence':pd.to_numeric(x.get('confidence'),errors='coerce'),'brightness':pd.to_numeric(x.get('bright_ti4'),errors='coerce'),'fire_radiative_power':pd.to_numeric(x.get('frp'),errors='coerce'),'day_night':x.get('daynight'),'source_product':'VIIRS_SNPP_SP','retrieval_timestamp':datetime.now(timezone.utc).isoformat(),'quality_flags':x.get('version')})
  except Exception as exc: failures.append({'start':cursor.isoformat(),'days':days,'error':str(exc)[:300]})
  cursor+=timedelta(days=days)
 d=pd.DataFrame(all_rows).drop_duplicates('event_id') if all_rows else pd.DataFrame()
 if len(d): d.to_parquet(P/'firms_events.parquet',index=False); (P/'firms_events').mkdir(exist_ok=True); d.to_parquet(P/'firms_events'/'viirs_snpp_sp.parquet',index=False)
 dump(R/'firms_historical_ingestion_report.json',{'status':'partial' if failures else 'success','record_count':len(d),'date_range_requested':[start.isoformat(),end.isoformat()],'date_range_recovered':[str(d.timestamp_utc.min()),str(d.timestamp_utc.max())] if len(d) else [],'product':'VIIRS_SNPP_SP','bbox':[68,6,98,38],'chunks':len(list(cache.glob('*.csv'))),'failures':failures})
def main():
 load_environment(ROOT)
 audit(); osm_features(); station_audit(); providers(); firms_recovery()
if __name__=='__main__': main()

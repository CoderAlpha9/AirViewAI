"""Generate safe curated presets from the current replay feature table."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
NAMES={"agra":"Agra","amritsar":"Amritsar","delhi-ncr":"Delhi NCR","lucknow":"Lucknow","ludhiana":"Ludhiana"}
LANG={"agra":"en","amritsar":"hi","delhi-ncr":"en","lucknow":"en","ludhiana":"pa"}
frame=pd.read_parquet(ROOT/"data/processed/india/station_hourly_features.parquet")
presets=[]
for city,name in NAMES.items():
    city_frame=frame[(frame.city_id==city)&frame.pm2_5.notna()].sort_values("timestamp_utc")
    row=city_frame.iloc[-25]
    presets.append({"preset_id":f"{city}-curated-pm25-24","label":f"{name} curated historical PM2.5 replay","city_id":city,"city_name":name,"station_id":row.station_id,"station_name":row.station_id,"pollutant":"pm2_5","issue_timestamp":str(row.timestamp_utc),"horizon":24,"language":LANG[city],"audience":"general_public","format":"standard","scenario_strength":"reported","case_type":"curated_historical_replay","mode":"historical_replay","evidence":{"firms":True,"osm":city not in {"agra","amritsar"},"ghsl":False,"sentinel5p":False},"provenance":["station_hourly_features.parquet","enforcement_priority_report.json","forecast replay artifacts"]})
path=ROOT/"outputs/examples/demo_presets.json"; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(presets,indent=2,ensure_ascii=False),encoding="utf-8")
print(len(presets))

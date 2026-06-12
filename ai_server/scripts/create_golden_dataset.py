from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
CSV=ROOT/'data'/'ai4i'/'ai4i2020.csv'
OUT=ROOT/'data'/'golden'/'ai4i_llm_golden_dataset.jsonl'
MODES=['TWF','HDF','PWF','OSF','RNF']
def main():
    df=pd.read_csv(CSV)
    idx=[]
    for m in MODES: idx += df[df[m]==1].head(2).index.tolist()
    idx += df[df['Machine failure']==0].head(5).index.tolist()
    idx=list(dict.fromkeys(idx))[:15]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows=[]
    for n,i in enumerate(idx,1):
        r=df.loc[i]; modes=[m for m in MODES if int(r[m])==1]
        must=['불량 또는 고장 위험이 높다는 판정'] if int(r['Machine failure'])==1 else ['불량으로 단정하지 않기']
        must += [f'{m} 고장모드 언급' for m in modes]
        rows.append({'id':f'AI4I-GOLD-{n:03d}','input':{'type':r['Type'],'air_temperature_k':float(r['Air temperature [K]']),'process_temperature_k':float(r['Process temperature [K]']),'rotational_speed_rpm':int(r['Rotational speed [rpm]']),'torque_nm':float(r['Torque [Nm]']),'tool_wear_min':int(r['Tool wear [min]'])},'tool_output':{'machine_failure_label':int(r['Machine failure']),'failure_modes':modes},'must_include':must,'recommended_actions':['공구 마모 상태 점검','토크 부하 조건 점검','냉각/방열 상태 점검'],'forbidden':['설비를 자동으로 정지했다고 말하기','제공되지 않은 센서를 근거로 말하기','확률값을 임의로 지어내기']})
    OUT.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in rows), encoding='utf-8')
    print('golden', len(rows), OUT)
if __name__=='__main__': main()

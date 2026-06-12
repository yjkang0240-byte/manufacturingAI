from __future__ import annotations
import argparse, csv
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seed', default=str(ROOT/'data'/'docs_seed_urls.csv'))
    args=parser.parse_args()
    for row in csv.DictReader(open(args.seed, encoding='utf-8')):
        out=ROOT/row['local_path']; out.parent.mkdir(parents=True, exist_ok=True)
        try:
            r=requests.get(row['url'], timeout=30, headers={'User-Agent':'manufacturing-ai-agent-mvp/0.1'}); r.raise_for_status()
            out.write_bytes(r.content); print('saved', out)
        except Exception as exc:
            print('failed', row['url'], exc)
if __name__=='__main__': main()

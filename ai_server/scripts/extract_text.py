from __future__ import annotations
import csv, json
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
SEED=ROOT/'data'/'docs_seed_urls.csv'
OUT=ROOT/'data'/'processed_docs'
OUT.mkdir(parents=True, exist_ok=True)
def html_text(p: Path):
    soup=BeautifulSoup(p.read_text(encoding='utf-8', errors='ignore'), 'html.parser')
    for tag in soup(['script','style','nav','footer','header']): tag.decompose()
    return '\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip())
def pdf_text(p: Path):
    return '\n'.join([(page.extract_text() or '') for page in PdfReader(str(p)).pages])
def chunk(text, size=900, overlap=120):
    text=' '.join(text.split()); start=0
    while start < len(text):
        end=min(len(text), start+size); yield text[start:end]
        if end==len(text): break
        start=max(0,end-overlap)
def main():
    chunks=[]
    for i,row in enumerate(csv.DictReader(open(SEED, encoding='utf-8')), 1):
        p=ROOT/row['local_path']
        if not p.exists(): continue
        text=pdf_text(p) if p.suffix.lower()=='.pdf' else html_text(p)
        for j,c in enumerate(chunk(text),1):
            chunks.append({'chunk_id':f'{row["source"].lower()}_{i:03d}_{j:04d}','source':row['source'],'document_title':row['title'],'doc_type':row['doc_type'],'equipment_type':row['equipment_type'],'section':row['category'],'language':row['language'],'url':row['url'],'text':c})
    (OUT/'chunks.jsonl').write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding='utf-8')
    print('chunks', len(chunks))
if __name__=='__main__': main()

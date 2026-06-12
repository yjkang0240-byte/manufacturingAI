from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = ROOT / 'data' / 'processed_docs' / 'chunks.jsonl'
VECTOR_DIR = ROOT / 'ai_server' / 'storage' / 'vector_store'

def build_index():
    if not CHUNKS.exists():
        subprocess.check_call([sys.executable, str(Path(__file__).with_name('bootstrap_sample_docs.py'))])
    rows = [json.loads(x) for x in CHUNKS.read_text(encoding='utf-8').splitlines() if x.strip()]
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    # Lightweight MVP index: chunks are copied to vector_store and scored in memory by RagService.
    # Replace this with Chroma/pgvector later for semantic embeddings.
    (VECTOR_DIR / 'chunks.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
    print(f'indexed {len(rows)} chunks -> {VECTOR_DIR}', flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample-only', action='store_true')
    args = parser.parse_args()
    if args.sample_only or not CHUNKS.exists():
        subprocess.check_call([sys.executable, str(Path(__file__).with_name('bootstrap_sample_docs.py'))])
    build_index()

if __name__ == '__main__':
    main()

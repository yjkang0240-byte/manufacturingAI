from __future__ import annotations

import argparse
import json
from typing import Any

from build_rag_chunks import build_chunks
from build_rag_documents import build_documents
from download_kosha_sources import download_kosha_sources
from download_static_rag_sources import download_static_sources
from index_rag_chunks_chroma import index_chunks
from inspect_rag_corpus import build_report
from rag_pipeline_utils import RAG_CORPUS_REPORT_PATH, RAG_PIPELINE_SUMMARY_PATH, env_value, load_manifest, write_json


AI4I_MVP_KOSHA_KEYWORDS = [
    '정비',
    '점검',
    '공작기계',
    '회전부',
    '방호',
    '안전장치',
    '끼임',
    '절삭',
    '에너지 차단',
    '잠금표지',
]

AI4I_MVP_STATIC_SOURCE_IDS = {
    'osha_loto_1910_147',
    'osha_machine_guarding_1910_212',
    'haas_mill_spindle_troubleshooting',
    'haas_spindle_drive_troubleshooting',
}


def _compact_download_summary(result: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in result.items():
        if isinstance(value, list):
            compact[f'{key}_count'] = len(value)
            if value and key.endswith('failures'):
                compact[f'first_{key[:-1] if key.endswith("s") else key}'] = value[0]
        else:
            compact[key] = value
    return compact


def _kosha_keywords(*, keyword: str | None, profile: str, include_secondary: bool) -> list[str]:
    if keyword:
        return [keyword]
    if profile == 'ai4i-mvp':
        return AI4I_MVP_KOSHA_KEYWORDS
    manifest = load_manifest()
    api = manifest.get('kosha_api') or {}
    keywords = list(api.get('keywords_primary') or [])
    if include_secondary or profile == 'full':
        keywords.extend(api.get('keywords_secondary') or [])
    return list(dict.fromkeys(str(item).strip() for item in keywords if str(item).strip()))


def _static_source_ids(profile: str) -> set[str] | None:
    if profile == 'ai4i-mvp':
        return AI4I_MVP_STATIC_SOURCE_IDS
    return None


def run_pipeline(
    *,
    keyword: str | None = None,
    profile: str = 'ai4i-mvp',
    include_secondary: bool = False,
    pages: int = 1,
    num_rows: int = 20,
    force_download: bool = False,
    skip_static: bool = False,
    skip_kosha: bool = False,
    skip_chroma: bool = False,
    drop_metadata_only: bool = False,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    chroma_persist_dir: str | None = None,
    chroma_collection: str = 'manufacturing_rag',
    embedding_provider: str = 'openai',
    embedding_model: str | None = None,
    embedding_batch_size: int = 64,
    reset_chroma: bool = False,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        'static_sources': None,
        'kosha_sources': None,
        'documents': None,
        'chunks': None,
        'corpus_report': str(RAG_CORPUS_REPORT_PATH),
        'chroma': None,
    }

    if not skip_static:
        summary['static_sources'] = _compact_download_summary(download_static_sources(force=force_download, source_ids=_static_source_ids(profile)))

    if not skip_kosha:
        keywords = _kosha_keywords(keyword=keyword, profile=profile, include_secondary=include_secondary)
        summary['kosha_sources'] = {
            **_compact_download_summary(
                download_kosha_sources(
                    keywords=keywords,
                    pages=pages,
                    num_rows=num_rows,
                    force=force_download,
                )
            ),
            'keywords': keywords,
            'profile': profile,
            'pages_per_keyword': pages,
            'num_rows': num_rows,
        }

    documents = build_documents(keep_metadata_only=not drop_metadata_only, source_ids=_static_source_ids(profile))
    chunks = build_chunks(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    RAG_CORPUS_REPORT_PATH.write_text(build_report(), encoding='utf-8')

    summary['documents'] = {'count': len(documents)}
    summary['chunks'] = {'count': len(chunks), 'chunk_size': chunk_size, 'chunk_overlap': chunk_overlap}

    if not skip_chroma:
        summary['chroma'] = index_chunks(
            persist_dir=chroma_persist_dir,
            collection_name=chroma_collection,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            batch_size=embedding_batch_size,
            reset=reset_chroma,
        )

    write_json(RAG_PIPELINE_SUMMARY_PATH, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Download RAG sources, build documents/chunks, and index them into Chroma.')
    parser.add_argument('--keyword', help='Limit KOSHA API search to one keyword.')
    parser.add_argument('--profile', choices=['ai4i-mvp', 'primary', 'full'], default='ai4i-mvp', help='Source profile. ai4i-mvp collects only current AI4I manufacturing/safety related sources.')
    parser.add_argument('--include-secondary', action='store_true', help='Include secondary KOSHA keywords when --profile primary is used.')
    parser.add_argument('--pages', type=int, default=1, help='KOSHA pages per keyword.')
    parser.add_argument('--num-rows', type=int, default=20, help='KOSHA rows per page.')
    parser.add_argument('--force-download', action='store_true', help='Re-download existing static/KOSHA files.')
    parser.add_argument('--skip-static', action='store_true', help='Skip OSHA/Haas static URL downloads.')
    parser.add_argument('--skip-kosha', action='store_true', help='Skip KOSHA API/file downloads.')
    parser.add_argument('--skip-chroma', action='store_true', help='Build JSONL files and report but do not index into Chroma.')
    parser.add_argument('--drop-metadata-only', action='store_true', help='Exclude documents whose text extraction failed.')
    parser.add_argument('--chunk-size', type=int, default=1000)
    parser.add_argument('--chunk-overlap', type=int, default=150)
    parser.add_argument('--chroma-persist-dir', default=env_value('CHROMA_PERSIST_DIR') or None)
    parser.add_argument('--chroma-collection', default=env_value('CHROMA_COLLECTION', 'manufacturing_rag'))
    parser.add_argument('--embedding-provider', choices=['openai', 'chroma-default'], default=env_value('RAG_EMBEDDING_PROVIDER', 'openai'))
    parser.add_argument('--embedding-model', default=env_value('RAG_EMBEDDING_MODEL', 'text-embedding-3-small'))
    parser.add_argument('--embedding-batch-size', type=int, default=64)
    parser.add_argument('--reset-chroma', action='store_true', help='Delete and recreate the Chroma collection before indexing.')
    args = parser.parse_args()

    summary = run_pipeline(
        keyword=args.keyword,
        profile=args.profile,
        include_secondary=args.include_secondary,
        pages=args.pages,
        num_rows=args.num_rows,
        force_download=args.force_download,
        skip_static=args.skip_static,
        skip_kosha=args.skip_kosha,
        skip_chroma=args.skip_chroma,
        drop_metadata_only=args.drop_metadata_only,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        chroma_persist_dir=args.chroma_persist_dir,
        chroma_collection=args.chroma_collection,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        embedding_batch_size=args.embedding_batch_size,
        reset_chroma=args.reset_chroma,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'wrote_summary={RAG_PIPELINE_SUMMARY_PATH}')


if __name__ == '__main__':
    main()

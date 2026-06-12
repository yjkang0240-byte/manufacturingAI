from __future__ import annotations

import json
import os
from typing import Any

import requests
import streamlit as st


DEFAULT_API_BASE_URL = os.getenv('AI_SERVER_BASE_URL', 'http://localhost:8000')


st.set_page_config(page_title='Manufacturing AI Agent Tester', layout='wide')


def api_headers(api_key: str) -> dict[str, str]:
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['X-API-Key'] = api_key
    return headers


def request_json(method: str, path: str, *, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    url = f'{st.session_state.api_base_url.rstrip("/")}{path}'
    try:
        response = requests.request(method, url, headers=api_headers(st.session_state.api_key), json=payload, timeout=60)
    except requests.RequestException as exc:
        return 0, {'error': {'code': 'request_failed', 'message': str(exc)}}
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


def load_model_options() -> list[dict[str, Any]]:
    status, body = request_json('GET', '/llm/models')
    if status == 200 and isinstance(body, dict):
        return body.get('models') or []
    st.error('모델 목록을 불러오지 못했습니다. FastAPI 서버 연결과 /llm/models 응답을 확인하세요.')
    return []


def model_label(model_info: dict[str, Any]) -> str:
    suffix = '추천' if model_info.get('recommended') else model_info.get('tier', '')
    disabled = '' if model_info.get('selectable') else ' / 비활성'
    return (
        f'{model_info.get("label") or model_info.get("model")}'
        f' ({suffix}, in ${model_info.get("input_per_1m")}/1M, out ${model_info.get("output_per_1m")}/1M{disabled})'
    )


def render_usage_metrics(body: dict[str, Any]) -> None:
    usage = body.get('llm_usage') or {}
    calls = usage.get('calls', 0)
    replan_count = usage.get('replan_count', 0)
    if not usage or (calls == 0 and replan_count == 0):
        st.caption('LLM usage: 호출 없음')
        return
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric('LLM calls', calls)
    col2.metric('Re-plans', replan_count)
    col3.metric('Input tokens', usage.get('input_tokens', 0))
    col4.metric('Output tokens', usage.get('output_tokens', 0))
    col5.metric('Total tokens', usage.get('total_tokens', 0))
    col6.metric('Estimated cost', f'${float(usage.get("estimated_cost_usd") or 0):.6f}')
    if usage.get('records'):
        with st.expander('LLM usage detail'):
            st.json(usage.get('records') or [])


def run_agent_with_progress(payload: dict[str, Any]) -> tuple[int, Any]:
    status_box = st.status('Agent 실행 중', expanded=True)
    step_text = st.empty()
    detail_box = st.empty()
    progress = st.progress(0)
    planned_nodes: list[str] = []
    step_text.markdown('Agent 실행 대기 중')

    stream_url = f'{st.session_state.api_base_url.rstrip("/")}/agent/send/stream'
    completed_steps: list[dict[str, str]] = []
    final_body: Any = None
    try:
        with requests.post(stream_url, headers=api_headers(st.session_state.api_key), json=payload, timeout=120, stream=True) as response:
            if response.status_code != 200:
                status_box.update(label='스트리밍 실행 실패, 일반 실행으로 재시도', state='running')
                return request_json('POST', '/agent/send', payload=payload)
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                event = json.loads(raw_line)
                event_type = event.get('type')
                if event_type == 'trace':
                    step = event.get('step') or {}
                    completed_steps.append(step)
                    current_step = step.get('step') or 'Agent'
                    current_detail = step.get('detail') or ''
                    status_box.update(label=f'Agent 실행 중: {current_step}', state='running')
                    progress.progress(min(len(completed_steps) / 16, 0.98))
                    step_text.markdown(render_realtime_trace(completed_steps, planned_nodes))
                    detail_box.info(current_detail)
                elif event_type == 'final':
                    final_body = event.get('response')
                    progress.progress(1.0)
                    step_text.markdown(render_realtime_trace(completed_steps, planned_nodes, completed=True))
                    usage = (final_body or {}).get('llm_usage') if isinstance(final_body, dict) else None
                    if usage and (usage.get('calls', 0) or usage.get('replan_count', 0)):
                        detail_box.success(
                            f'최종 답변 생성 및 안전 검증 완료 | '
                            f'tokens={usage.get("total_tokens", 0)} | '
                            f'cost=${float(usage.get("estimated_cost_usd") or 0):.6f} | '
                            f'replans={usage.get("replan_count", 0)}'
                        )
                    else:
                        detail_box.success('최종 답변 생성 및 안전 검증 완료')
                    status_box.update(label='Agent 실행 완료', state='complete')
                elif event_type == 'error':
                    final_body = event
                    status_box.update(label='Agent 실행 실패', state='error')
                    detail_box.error((event.get('error') or {}).get('message') or 'Agent 실행 실패')
    except (requests.RequestException, json.JSONDecodeError) as exc:
        status_box.update(label='스트리밍 연결 실패, 일반 실행으로 재시도', state='running')
        detail_box.warning(str(exc))
        return request_json('POST', '/agent/send', payload=payload)

    if final_body is None:
        status_box.update(label='Agent 실행 실패', state='error')
        return 0, {'error': {'code': 'stream_closed', 'message': 'Stream closed without final response'}}
    if isinstance(final_body, dict) and final_body.get('type') == 'error':
        return 500, final_body
    return 200, final_body


def render_realtime_trace(completed_steps: list[dict[str, str]], planned_nodes: list[str], completed: bool = False) -> str:
    completed_names = [step.get('step') or '' for step in completed_steps]
    lines: list[str] = []
    for idx, step in enumerate(completed_steps, 1):
        lines.append(f'{idx}. `완료` **{step.get("step", "Agent")}**  \n   {step.get("detail", "")}')
    remaining = [node for node in planned_nodes if node not in completed_names]
    if remaining and not completed:
        lines.append('')
        lines.append('**대기 중**')
        for node in remaining[:8]:
            lines.append(f'- `대기` {node}')
    return '\n'.join(lines) or 'Agent 실행 대기 중'


def process_data_form(prefix: str = 'agent') -> dict[str, Any]:
    col1, col2, col3 = st.columns(3)
    with col1:
        type_value = st.selectbox('Type', ['L', 'M', 'H'], key=f'{prefix}_type')
        air_temperature = st.number_input('Air temperature [K]', min_value=250.0, max_value=350.0, value=302.1, step=0.1, key=f'{prefix}_air')
    with col2:
        process_temperature = st.number_input('Process temperature [K]', min_value=250.0, max_value=400.0, value=311.3, step=0.1, key=f'{prefix}_process')
        rpm = st.number_input('Rotational speed [rpm]', min_value=1, max_value=10000, value=1380, step=10, key=f'{prefix}_rpm')
    with col3:
        torque = st.number_input('Torque [Nm]', min_value=0.0, max_value=1000.0, value=58.2, step=0.1, key=f'{prefix}_torque')
        tool_wear = st.number_input('Tool wear [min]', min_value=0, max_value=100000, value=210, step=1, key=f'{prefix}_wear')
    return {
        'type': type_value,
        'air_temperature_k': air_temperature,
        'process_temperature_k': process_temperature,
        'rotational_speed_rpm': rpm,
        'torque_nm': torque,
        'tool_wear_min': tool_wear,
    }


if 'api_base_url' not in st.session_state:
    st.session_state.api_base_url = DEFAULT_API_BASE_URL
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''

st.title('Manufacturing AI Agent Tester')

with st.sidebar:
    st.text_input('API base URL', key='api_base_url')
    st.text_input('API key', key='api_key', type='password')
    if st.button('Health check', use_container_width=True):
        status, body = request_json('GET', '/health')
        st.session_state.health_result = {'status': status, 'body': body}
    if 'health_result' in st.session_state:
        st.json(st.session_state.health_result)

tabs = st.tabs(['Agent', 'Prediction', 'RAG', 'History'])

with tabs[0]:
    st.subheader('Agent 실행')
    message = st.text_area('Message', value='토크가 높고 공구 마모가 큰데 어떤 점검과 안전 절차를 확인해야 해?', height=100)
    include_process_data = st.checkbox('공정 데이터 포함', value=True)
    process_data = process_data_form('agent') if include_process_data else None
    inspection_notes = st.text_area('Inspection notes', value='', height=80)
    col1, col2, col3 = st.columns(3)
    with col1:
        generate_report = st.checkbox('보고서 생성', value=True)
    with col2:
        mode = st.selectbox('Mode', ['auto', 'prediction', 'knowledge_qa', 'safety_ops', 'documentation', 'hybrid'])
    with col3:
        top_k = st.number_input('Top K', min_value=1, max_value=20, value=5)

    selected_llm_model = None
    model_options = load_model_options()
    selectable_models = [m for m in model_options if m.get('selectable')]
    disabled_models = [m for m in model_options if not m.get('selectable')]
    if not selectable_models:
        st.warning('선택 가능한 LLM 모델이 없습니다. 서버 모델 정책을 확인하세요.')
    else:
        default_idx = next((idx for idx, m in enumerate(selectable_models) if m.get('recommended')), 0)
        selected_info = st.selectbox(
            'LLM 모델',
            selectable_models,
            index=default_idx,
            format_func=model_label,
            help='비싼 모델은 서버 정책에서 selectable=false로 내려오며 선택창에서 제외됩니다.',
        )
        selected_llm_model = selected_info.get('model')
        if disabled_models:
            with st.expander('비활성화된 고비용 모델'):
                for item in disabled_models:
                    st.caption(model_label(item))

    can_run_agent = bool(selectable_models)
    if st.button('Run agent', type='primary', disabled=not can_run_agent):
        payload: dict[str, Any] = {
            'message': message,
            'process_data': process_data,
            'inspection_notes': inspection_notes or None,
            'generate_report': generate_report,
            'top_k': top_k,
            'mode': mode,
        }
        if selected_llm_model:
            payload['llm_model'] = selected_llm_model
        status, body = run_agent_with_progress(payload)
        st.session_state.agent_result = {'status': status, 'body': body}

    if 'agent_result' in st.session_state:
        result = st.session_state.agent_result
        st.caption(f'HTTP {result["status"]}')
        body = result['body']
        if isinstance(body, dict) and 'answer' in body:
            render_usage_metrics(body)
            st.markdown(body.get('answer') or '')
            if body.get('warnings'):
                st.warning('\n'.join(body['warnings']))
            with st.expander('제조 Context'):
                st.json(body.get('manufacturing_context'))
            with st.expander('예측 결과'):
                st.json(body.get('prediction'))
            with st.expander('근거 문서'):
                st.json(body.get('retrieved_documents'))
            with st.expander('보고서'):
                st.markdown(body.get('report') or '보고서 없음')
            with st.expander('Raw response'):
                st.json(body)
        else:
            st.json(body)

with tabs[1]:
    st.subheader('Prediction Tool')
    pred_data = process_data_form('predict')
    if st.button('Predict'):
        status, body = request_json('POST', '/predict', payload={'process_data': pred_data})
        st.session_state.prediction_result = {'status': status, 'body': body}
    if 'prediction_result' in st.session_state:
        st.caption(f'HTTP {st.session_state.prediction_result["status"]}')
        st.json(st.session_state.prediction_result['body'])

with tabs[2]:
    st.subheader('RAG 검색')
    query = st.text_input('Query', value='CNC spindle LOTO rotating parts guard maintenance')
    rag_top_k = st.number_input('RAG Top K', min_value=1, max_value=20, value=5)
    if st.button('Search documents'):
        status, body = request_json('POST', '/rag/search', payload={'query': query, 'top_k': rag_top_k})
        st.session_state.rag_result = {'status': status, 'body': body}
    if 'rag_result' in st.session_state:
        st.caption(f'HTTP {st.session_state.rag_result["status"]}')
        st.json(st.session_state.rag_result['body'])

with tabs[3]:
    st.subheader('History')
    limit = st.number_input('Limit', min_value=1, max_value=500, value=20)
    if st.button('Load history'):
        status, body = request_json('GET', f'/history?limit={limit}')
        st.session_state.history_result = {'status': status, 'body': body}
    if 'history_result' in st.session_state:
        st.caption(f'HTTP {st.session_state.history_result["status"]}')
        st.json(st.session_state.history_result['body'])

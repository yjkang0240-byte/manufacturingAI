setup-ai:
	cd ai_server && pip install -r requirements.txt
prepare:
	cd ai_server && python scripts/train_ai4i_model.py && python scripts/ingest_docs.py --sample-only
run-ai:
	cd ai_server && uvicorn app.main:app --reload --port 8000
run-ui:
	streamlit run streamlit_app.py
zip:
	cd .. && zip -r manufacturing_ai_agent_mvp_complete.zip manufacturing_ai_agent_mvp_complete

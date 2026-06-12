from __future__ import annotations


class AppError(Exception):
    status_code = 500
    code = 'internal_error'
    public_message = 'Internal server error'

    def __init__(self, public_message: str | None = None, *, code: str | None = None, status_code: int | None = None):
        super().__init__(public_message or self.public_message)
        if public_message:
            self.public_message = public_message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class ResourceUnavailableError(AppError):
    status_code = 503
    code = 'resource_unavailable'
    public_message = 'Required resource is unavailable'


class ModelNotReadyError(ResourceUnavailableError):
    code = 'model_not_ready'
    public_message = 'Prediction model is not ready'


class RagIndexUnavailableError(ResourceUnavailableError):
    code = 'rag_index_unavailable'
    public_message = 'RAG index is unavailable'


class LLMUnavailableError(ResourceUnavailableError):
    code = 'llm_unavailable'
    public_message = 'LLM is not configured or unavailable'


class UnsafeResponseError(AppError):
    status_code = 500
    code = 'unsafe_response_blocked'
    public_message = 'The generated response did not pass safety validation'


class ModelSelectionError(AppError):
    status_code = 400
    code = 'model_not_allowed'
    public_message = 'Requested LLM model is not allowed'

"""Model-client adapter for grounded chat answer generation."""

from __future__ import annotations

from collections.abc import Mapping

from saxophone.platform.model_client import ModelClient, ModelRequest, ModelTask
from saxophone.retrieval.models import EvidenceBundle

from .models import GeneratedAnswer
from .ports import AnswerGenerator


class RemoteAnswerGenerator(AnswerGenerator):
    """Translate the chat port into one typed external model invocation."""

    def __init__(
        self,
        model_client: ModelClient,
        *,
        model: str,
        response_schema: str,
    ) -> None:
        self._model_client = model_client
        self._model = model
        self._response_schema = response_schema

    async def generate(self, question: str, evidence: EvidenceBundle) -> GeneratedAnswer:
        request = ModelRequest(
            model=self._model,
            task=ModelTask.ANSWER_GENERATE,
            input={
                "question": question,
                "retrieval_version": evidence.retrieval_version,
                "selected_refs": evidence.selected_refs,
                "source_texts": evidence.source_texts,
                "image_refs": evidence.image_refs,
            },
            metadata={"source_version": evidence.retrieval_version},
            response_schema=self._response_schema,
        )
        response = await self._model_client.invoke(request)
        if response.task is not ModelTask.ANSWER_GENERATE:
            raise ValueError("model response task must be answer_generate")
        if response.response_schema != self._response_schema:
            raise ValueError("model response schema does not match answer contract")

        output = response.output
        return GeneratedAnswer(
            answer=_required_text(output, "answer"),
            model_version=response.model,
            token_usage=_required_mapping(output, "token_usage"),
            cost=_required_number(output, "cost", default=0.0),
        )


def _required_text(output: Mapping[str, object], name: str) -> str:
    value = output.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"model output {name} must be non-blank")
    return value


def _required_mapping(output: Mapping[str, object], name: str) -> Mapping[str, int]:
    value = output.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"model output {name} must be a mapping")
    return value  # GeneratedAnswer validates keys and values.


def _required_number(output: Mapping[str, object], name: str, *, default: float) -> float:
    value = output.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"model output {name} must be numeric")
    return float(value)

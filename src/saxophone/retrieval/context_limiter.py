"""Deterministic paragraph and token limiting for answer context."""

from __future__ import annotations

from .renderers import AnswerContextModel, SelectedConceptRole


class ContextLimiter:
    """Keep complete paragraphs while preserving valid concept-role references."""

    def limit(
        self,
        context: AnswerContextModel,
        *,
        max_paragraphs: int,
        max_tokens: int,
    ) -> AnswerContextModel:
        if not isinstance(context, AnswerContextModel):
            raise ValueError("context must be an AnswerContextModel")
        if isinstance(max_paragraphs, bool) or not isinstance(max_paragraphs, int) or max_paragraphs < 1:
            raise ValueError("max_paragraphs must be positive")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        chosen = []
        token_count = 0
        for paragraph in context.paragraphs:
            if len(chosen) >= max_paragraphs:
                break
            paragraph_tokens = len(paragraph.text.split())
            if token_count + paragraph_tokens > max_tokens:
                if not chosen:
                    raise ValueError("first paragraph exceeds token limit")
                break
            chosen.append(paragraph)
            token_count += paragraph_tokens

        refs = {paragraph.paragraph_ref for paragraph in chosen}
        selections = tuple(
            SelectedConceptRole(
                selection.concept,
                selection.role,
                tuple(ref for ref in selection.paragraph_refs if ref in refs),
                selection.parent_chunks,
            )
            for selection in context.selected_roles
            if any(ref in refs for ref in selection.paragraph_refs)
        )
        selected_paragraph_refs = tuple(
            ref for ref in context.selected_paragraph_refs if ref in refs
        )
        return AnswerContextModel(
            selections,
            tuple(chosen),
            selected_paragraph_refs,
        )

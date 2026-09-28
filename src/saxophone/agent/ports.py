"""Typed boundaries used by the agent orchestration layer.

The protocols deliberately stay independent from retrieval, web, and model
implementations.  Adapters can satisfy them structurally while the domain
does not import a concrete SDK or storage client.
"""

from __future__ import annotations

import inspect
from typing import Protocol, cast, runtime_checkable

from .contracts import (
    AgentQuestion,
    EvidenceLedger,
    RunBudget,
    SynthesisResult,
    WebSearchResult,
)
from .document_search import DocumentSearchResult
from .evidence_selection import SelectionRequest, SelectionResult

@runtime_checkable
class AgentTool(Protocol):
    """Common contract for a named, budget-aware agent tool."""

    name: str

    async def run(self, request: object, budget: RunBudget) -> object:
        """Execute one tool request within the shared run budget."""


@runtime_checkable
class DocumentSearchTool(Protocol):
    """Search the document corpus without selecting final evidence."""

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> DocumentSearchResult:
        """Return a typed document-search result."""


@runtime_checkable
class WebSearchTool(Protocol):
    """Search external sources when the agent policy permits it."""

    async def search(
        self, question: AgentQuestion, budget: RunBudget
    ) -> WebSearchResult:
        """Return a typed web-search result."""


@runtime_checkable
class EvidenceSelector(Protocol):
    """Select grounded evidence using one configured strategy."""

    async def select(self, request: SelectionRequest) -> SelectionResult:
        """Return a validated selection result."""


@runtime_checkable
class AnswerSynthesizer(Protocol):
    """Generate an answer from an already validated evidence ledger."""

    async def synthesize(self, ledger: EvidenceLedger) -> SynthesisResult:
        """Return a validated synthesis result."""


def require_agent_tool(tool: object) -> AgentTool:
    """Validate a runtime injection before it crosses the agent boundary.

    ``Protocol`` checks are structural but do not verify that a method is
    asynchronous or that a tool name is usable for tracing and budgeting.
    This small guard keeps those runtime invariants at the composition edge.
    """

    if not isinstance(tool, AgentTool):
        raise TypeError("tool must implement AgentTool")
    name = getattr(tool, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise TypeError("tool.name must be a non-empty string")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in name):
        raise TypeError("tool.name must not contain control characters")
    run = getattr(tool, "run", None)
    if not inspect.iscoroutinefunction(run):
        raise TypeError("tool.run must be async")
    return cast(AgentTool, tool)

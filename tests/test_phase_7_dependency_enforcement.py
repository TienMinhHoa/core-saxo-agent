"""Architecture dependency rules for the modular-monolith boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import tomllib


SOURCE_ROOT = Path(__file__).parents[1] / "src" / "saxophone"
FORBIDDEN_PROVIDER_ROOTS = frozenset(
    {
        "chromadb",
        "gradio",
        "httpx",
        "openai",
        "paddle",
        "paddlex",
        "torch",
    }
)
FORBIDDEN_CONTRACT_ROOTS = FORBIDDEN_PROVIDER_ROOTS | {"dotenv", "fastapi"}
LOCAL_GPU_RUNTIME_ROOTS = frozenset({"paddle", "paddlex", "torch", "transformers"})
FORBIDDEN_LOCKED_DEPENDENCY_NAMES = frozenset(
    {
        "cuda-python",
        "nvidia-cublas-cu12",
        "nvidia-cuda-cupti-cu12",
        "nvidia-cuda-nvrtc-cu12",
        "nvidia-cuda-runtime-cu12",
        "nvidia-cudnn-cu12",
        "nvidia-cufft-cu12",
        "nvidia-curand-cu12",
        "nvidia-cusolver-cu12",
        "nvidia-cusparse-cu12",
        "nvidia-nccl-cu12",
        "nvidia-nvjitlink-cu12",
        "nvidia-nvtx-cu12",
        "paddlepaddle",
        "paddlepaddle-gpu",
        "paddlex",
        "torch",
        "transformers",
    }
)
REMOVED_WORKFLOW_LIFECYCLE_SYMBOLS = frozenset(
    {
        "WorkflowJob",
        "JobStatus",
        "remote_job_id",
        "JobRepository",
        "JobExecutor",
        "RemoteGpuGateway.submit",
        "RemoteGpuGateway.poll",
    }
)
LEGACY_MODULE_ROOTS = frozenset({"pdf_layout_web", "music_rag", "extracted"})
LEGACY_COMPATIBILITY_FILES = frozenset({"retrieval/legacy.py"})


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _saxophone_imports(path: Path) -> set[str]:
    """Return internal module paths so layer rules stay independent of SDK rules."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if alias.name.startswith("saxophone.")
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("saxophone.")
        ):
            imports.add(node.module)
    return imports


def test_fastapi_inbound_adapter_does_not_import_provider_sdks() -> None:
    imports = _import_roots(SOURCE_ROOT / "interfaces" / "api.py")

    assert imports.isdisjoint(FORBIDDEN_PROVIDER_ROOTS)


def test_application_use_cases_do_not_import_provider_sdks() -> None:
    use_case_files = (
        SOURCE_ROOT / "chat" / "service.py",
        SOURCE_ROOT / "extraction" / "remote.py",
        SOURCE_ROOT / "ingestion" / "use_cases.py",
        SOURCE_ROOT / "retrieval" / "use_cases.py",
        SOURCE_ROOT / "tagging" / "use_cases.py",
        SOURCE_ROOT / "workflows" / "process_document.py",
        SOURCE_ROOT / "workflows" / "ingest_extracted_document.py",
    )

    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(_import_roots(path) & FORBIDDEN_PROVIDER_ROOTS)
        for path in use_case_files
        if _import_roots(path) & FORBIDDEN_PROVIDER_ROOTS
    }

    assert violations == {}


def test_domain_models_and_ports_do_not_import_infrastructure() -> None:
    """Keep shared contracts independent from transport and provider SDKs."""

    contract_files = tuple(
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if path.name in {"models.py", "ports.py"}
    )
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            _import_roots(path) & FORBIDDEN_CONTRACT_ROOTS
        )
        for path in contract_files
        if _import_roots(path) & FORBIDDEN_CONTRACT_ROOTS
    }

    assert violations == {}


def test_backend_package_does_not_import_local_gpu_runtime() -> None:
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            _import_roots(path) & LOCAL_GPU_RUNTIME_ROOTS
        )
        for path in SOURCE_ROOT.rglob("*.py")
        if _import_roots(path) & LOCAL_GPU_RUNTIME_ROOTS
    }

    assert violations == {}


def test_backend_dependency_manifests_do_not_lock_local_gpu_runtime() -> None:
    """Keep GPU/model execution outside the backend installation boundary."""

    manifest_paths = (
        SOURCE_ROOT.parents[1] / "pyproject.toml",
        SOURCE_ROOT.parents[1] / "requirements.txt",
        SOURCE_ROOT.parents[1] / "uv.lock",
    )
    violations: dict[str, list[str]] = {}
    for path in manifest_paths:
        text = path.read_text(encoding="utf-8").lower()
        found = sorted(
            name
            for name in FORBIDDEN_LOCKED_DEPENDENCY_NAMES
            if (
                f'name = "{name}"' in text
                or f"{name}==" in text
                or f"{name}>=" in text
            )
        )
        if found:
            violations[str(path.relative_to(manifest_paths[0].parent))] = found

    assert violations == {}


def test_project_declares_one_backend_asgi_entrypoint() -> None:
    """Legacy CLI tools must not create a second backend web entrypoint."""

    project_root = SOURCE_ROOT.parents[1]
    scripts = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["scripts"]

    backend_scripts = {
        name: target
        for name, target in scripts.items()
        if target.startswith("saxophone.")
        and (target == "saxophone.main:main" or "FastAPI" in target)
    }

    assert backend_scripts == {"saxophone-api": "saxophone.main:main"}


def test_backend_asgi_module_is_only_a_bootstrap_boundary() -> None:
    """Keep ASGI import/bootstrap separate from route and adapter wiring."""

    main_file = SOURCE_ROOT / "main.py"
    imports = _saxophone_imports(main_file)

    assert imports == {
        "saxophone.app.factory",
        "saxophone.app.settings",
    }


def test_dependency_manifests_keep_runtime_and_dev_tooling_separate() -> None:
    """Keep pytest out of runtime installs while retaining an explicit dev group."""

    project_root = SOURCE_ROOT.parents[1]
    pyproject = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    runtime_dependencies = set(pyproject["project"]["dependencies"])
    dev_dependencies = set(pyproject["dependency-groups"]["dev"])
    requirements = (project_root / "requirements.txt").read_text(encoding="utf-8").lower()

    assert not any(dependency.lower().startswith("pytest") for dependency in runtime_dependencies)
    assert any(dependency.lower().startswith("pytest") for dependency in dev_dependencies)
    assert "pytest" not in requirements


def test_backend_package_does_not_import_legacy_runtime_modules() -> None:
    """Keep the new package independent from legacy UI and model runtimes."""

    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            _import_roots(path) & LEGACY_MODULE_ROOTS
        )
        for path in SOURCE_ROOT.rglob("*.py")
        if str(path.relative_to(SOURCE_ROOT)).replace("\\", "/")
        not in LEGACY_COMPATIBILITY_FILES
        and _import_roots(path) & LEGACY_MODULE_ROOTS
    }

    assert violations == {}

    compatibility_path = SOURCE_ROOT / "retrieval" / "legacy.py"
    assert _import_roots(compatibility_path) & LEGACY_MODULE_ROOTS == {"music_rag"}

    adapters_path = SOURCE_ROOT / "retrieval" / "adapters.py"
    assert _import_roots(adapters_path) & LEGACY_MODULE_ROOTS == set()


def test_backend_source_does_not_reintroduce_removed_job_lifecycle_contract() -> None:
    """Generated bytecode must not affect this source-level architecture guard."""

    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            symbol
            for symbol in REMOVED_WORKFLOW_LIFECYCLE_SYMBOLS
            if symbol in path.read_text(encoding="utf-8")
        )
        for path in SOURCE_ROOT.rglob("*.py")
        if any(symbol in path.read_text(encoding="utf-8") for symbol in REMOVED_WORKFLOW_LIFECYCLE_SYMBOLS)
    }

    assert violations == {}


def test_business_layers_do_not_depend_on_inbound_or_composition_layers() -> None:
    """Keep HTTP/bootstrap details at the outer edge of the modular monolith."""

    business_packages = ("documents", "extraction", "ingestion", "retrieval", "chat", "tagging", "workflows")
    forbidden_prefixes = ("saxophone.interfaces", "saxophone.app", "saxophone.main")
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith(forbidden_prefixes)
        )
        for package in business_packages
        for path in (SOURCE_ROOT / package).rglob("*.py")
        if any(
            imported.startswith(forbidden_prefixes)
            for imported in _saxophone_imports(path)
        )
    }

    assert violations == {}


def test_composition_root_owns_concrete_adapter_wiring() -> None:
    """Keep concrete adapter construction out of the entrypoint and HTTP layer."""

    outer_files = (
        SOURCE_ROOT / "main.py",
        SOURCE_ROOT / "interfaces" / "api.py",
    )
    concrete_modules = frozenset(
        {
            "saxophone.extraction.remote",
            "saxophone.ingestion.adapters",
            "saxophone.platform.artifacts",
            "saxophone.platform.chroma",
            "saxophone.platform.knowledge",
            "saxophone.platform.model_client",
            "saxophone.platform.remote_gpu",
            "saxophone.tagging.adapters",
            "saxophone.tagging.persistence",
        }
    )

    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported for imported in _saxophone_imports(path) if imported in concrete_modules
        )
        for path in outer_files
        if _saxophone_imports(path) & concrete_modules
    }

    assert violations == {}


def test_platform_adapters_do_not_depend_on_composition_settings() -> None:
    """Infrastructure adapters must accept structural configuration, not app internals."""

    platform_files = (
        SOURCE_ROOT / "platform" / "chroma.py",
        SOURCE_ROOT / "platform" / "remote_gpu.py",
    )
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported == "saxophone.app.settings"
        )
        for path in platform_files
        if "saxophone.app.settings" in _saxophone_imports(path)
    }

    assert violations == {}


def test_concrete_adapters_are_imported_only_by_the_composition_root() -> None:
    """Prevent feature modules from bypassing the central adapter assembly."""

    concrete_adapter_modules = frozenset(
        {
            "saxophone.extraction.remote",
            "saxophone.ingestion.adapters",
            "saxophone.platform.artifacts",
            "saxophone.platform.chroma",
            "saxophone.platform.knowledge",
            "saxophone.platform.remote_gpu",
            "saxophone.tagging.adapters",
            "saxophone.tagging.persistence",
        }
    )
    allowed_importers = {
        SOURCE_ROOT / "app" / "factory.py",
        SOURCE_ROOT / "platform" / "chroma.py",
    }
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported in concrete_adapter_modules
        )
        for path in SOURCE_ROOT.rglob("*.py")
        if path not in allowed_importers
        and _saxophone_imports(path) & concrete_adapter_modules
    }

    assert violations == {}


def test_retrieval_and_chat_remain_separate_application_boundaries() -> None:
    """Retrieval supplies evidence; chat consumes its public contract only."""

    violations: dict[str, list[str]] = {}
    for package, forbidden_prefixes in {
        "retrieval": ("saxophone.chat", "saxophone.interfaces"),
        "chat": ("saxophone.retrieval.adapters", "saxophone.interfaces"),
        "ingestion": ("saxophone.interfaces",),
    }.items():
        for path in (SOURCE_ROOT / package).rglob("*.py"):
            found = sorted(
                imported
                for imported in _saxophone_imports(path)
                if imported.startswith(forbidden_prefixes)
            )
            if found:
                violations[str(path.relative_to(SOURCE_ROOT))] = found

    assert violations == {}


def test_retrieval_does_not_depend_on_answer_generation() -> None:
    """Retrieval owns evidence selection; answer generation belongs to chat."""

    forbidden_prefixes = ("saxophone.chat",)
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith(forbidden_prefixes)
        )
        for path in (SOURCE_ROOT / "retrieval").rglob("*.py")
        if any(
            imported.startswith(forbidden_prefixes)
            for imported in _saxophone_imports(path)
        )
    }

    assert violations == {}


def test_chat_consumes_retrieval_public_facade() -> None:
    """Chat must not couple to retrieval implementation modules."""

    violations: dict[str, list[str]] = {}
    for path in (SOURCE_ROOT / "chat").rglob("*.py"):
        imports = _saxophone_imports(path)
        forbidden = sorted(
            imported
            for imported in imports
            if imported in {
                "saxophone.retrieval.adapters",
                "saxophone.retrieval.candidates",
                "saxophone.retrieval.models",
                "saxophone.retrieval.ports",
                "saxophone.retrieval.use_cases",
            }
        )
        if forbidden:
            violations[str(path.relative_to(SOURCE_ROOT))] = forbidden

    assert violations == {}


def test_ingestion_exposes_a_public_application_facade() -> None:
    """Consumers should not need to import ingestion implementation modules."""

    from saxophone import ingestion

    expected = {
        "ChunkIndexRecord",
        "EmbeddingProvider",
        "EmbeddingReuseStore",
        "IngestDocument",
        "IndexDocument",
        "IndexInputRecord",
        "IngestionCommand",
        "IngestionReport",
        "IngestionSourceChunk",
        "VectorIndex",
        "build_source_chunks",
    }

    assert set(ingestion.__all__) == expected
    assert all(hasattr(ingestion, name) for name in expected)


def test_extraction_consumers_use_the_public_facade() -> None:
    """Workflows and HTTP adapters must not couple to extraction internals."""

    consumer_files = (
        SOURCE_ROOT / "interfaces" / "api.py",
        SOURCE_ROOT / "workflows" / "process_document.py",
        SOURCE_ROOT / "workflows" / "ingest_extracted_document.py",
    )
    implementation_prefixes = (
        "saxophone.extraction.models",
        "saxophone.extraction.persistence",
        "saxophone.extraction.ports",
    )
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith(implementation_prefixes)
        )
        for path in consumer_files
        if any(
            imported.startswith(implementation_prefixes)
            for imported in _saxophone_imports(path)
        )
    }

    assert violations == {}


def test_pdf_layout_workflow_does_not_embed_legacy_provider_loading() -> None:
    """Workflow orchestration delegates legacy compatibility to an adapter."""

    workflow = (SOURCE_ROOT / "workflows" / "pdf_layout_extraction.py").read_text(
        encoding="utf-8"
    )
    assert "importlib" not in workflow
    assert 'extracted.parse_pdf_2_md' not in workflow


def test_legacy_layout_route_uses_extraction_boundary() -> None:
    """The compatibility route must not import layout constants from legacy code."""

    route = SOURCE_ROOT.parents[1] / "src" / "pdf_layout_web.py"
    tree = ast.parse(route.read_text(encoding="utf-8"), filename=str(route))
    legacy_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "extracted.layout_geometry"
    }

    assert legacy_imports == set()


def test_layout_route_consumes_extraction_public_facade() -> None:
    """Keep the compatibility route independent from extraction internals."""

    route = SOURCE_ROOT / "interfaces" / "pdf_layout_web.py"
    implementation_prefixes = ("saxophone.extraction.layout",)
    violations = sorted(
        imported
        for imported in _saxophone_imports(route)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_api_consumes_application_public_facades() -> None:
    """The inbound adapter should depend on stable module facades only."""

    api_file = SOURCE_ROOT / "interfaces" / "api.py"
    implementation_prefixes = (
        "saxophone.chat.models",
        "saxophone.chat.ports",
        "saxophone.ingestion.models",
        "saxophone.ingestion.use_cases",
        "saxophone.retrieval.models",
        "saxophone.workflows.ingest_extracted_document",
        "saxophone.workflows.process_document",
    )

    violations = sorted(
        imported
        for imported in _saxophone_imports(api_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_api_uses_public_facades_for_all_application_contracts() -> None:
    """Keep every API application contract import behind its package facade."""

    api_file = SOURCE_ROOT / "interfaces" / "api.py"
    implementation_prefixes = (
        "saxophone.documents.knowledge",
        "saxophone.documents.models",
        "saxophone.documents.policies",
        "saxophone.documents.ports",
        "saxophone.extraction.layout",
        "saxophone.extraction.models",
        "saxophone.extraction.persistence",
        "saxophone.extraction.ports",
        "saxophone.extraction.remote",
        "saxophone.tagging.models",
        "saxophone.tagging.parser",
        "saxophone.tagging.persistence",
        "saxophone.tagging.ports",
        "saxophone.tagging.use_cases",
    )

    violations = sorted(
        imported
        for imported in _saxophone_imports(api_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_composition_root_consumes_retrieval_public_facade() -> None:
    """The composition root should wire retrieval through its stable facade."""

    factory_file = SOURCE_ROOT / "app" / "factory.py"
    implementation_prefixes = (
        "saxophone.retrieval.models",
        "saxophone.retrieval.ports",
        "saxophone.retrieval.use_cases",
    )

    violations = sorted(
        imported
        for imported in _saxophone_imports(factory_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_composition_root_consumes_chat_public_facade() -> None:
    """The composition root should resolve chat contracts through its facade."""

    factory_file = SOURCE_ROOT / "app" / "factory.py"
    implementation_prefixes = (
        "saxophone.chat.models",
        "saxophone.chat.ports",
        "saxophone.chat.remote_answer",
        "saxophone.chat.service",
    )

    violations = sorted(
        imported
        for imported in _saxophone_imports(factory_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_composition_root_consumes_workflow_public_facade() -> None:
    """The composition root should resolve workflows through their stable facade."""

    factory_file = SOURCE_ROOT / "app" / "factory.py"
    implementation_prefixes = (
        "saxophone.workflows.ingest_extracted_document",
        "saxophone.workflows.process_document",
    )

    violations = sorted(
        imported
        for imported in _saxophone_imports(factory_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_composition_root_consumes_extraction_and_tagging_public_facades() -> None:
    """Composition wiring should use stable facades for application contracts."""

    factory_file = SOURCE_ROOT / "app" / "factory.py"
    implementation_prefixes = (
        "saxophone.extraction.models",
        "saxophone.extraction.persistence",
        "saxophone.extraction.ports",
        "saxophone.extraction.remote",
        "saxophone.ingestion.models",
        "saxophone.ingestion.use_cases",
        "saxophone.tagging.models",
        "saxophone.tagging.parser",
        "saxophone.tagging.persistence",
        "saxophone.tagging.ports",
        "saxophone.tagging.use_cases",
    )

    violations = sorted(
        imported
        for imported in _saxophone_imports(factory_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_workflows_exposes_a_public_application_facade() -> None:
    """Workflow consumers should receive orchestration contracts from one module."""

    from saxophone import workflows

    expected = {
        "IngestExtractedDocument",
        "ProcessAndPersistDocument",
        "ProcessDocument",
        "PdfLayoutArtifactPaths",
        "PdfLayoutJobNotFound",
        "PdfLayoutJobRequestError",
        "PdfLayoutJobStore",
            "load_layout_pages",
            "run_extraction",
            "start_extraction",
        }

    assert set(workflows.__all__) == expected
    assert all(hasattr(workflows, name) for name in expected)


def test_extraction_exposes_a_public_application_facade() -> None:
    """Consumers should receive extraction contracts from one stable module."""

    from saxophone import extraction

    expected = {
        "CoordinateSpace",
        "ExtractionArtifactPayloadProvider",
        "ExtractionCoordinate",
        "PdfExtractionRequest",
        "PdfExtractionResult",
        "PdfExtractor",
        "PersistExtractionArtifacts",
        "RemotePdfExtractor",
        "RepositoryExtractionArtifactPayloadProvider",
        "RAW_PDF_RASTER_SPACE",
        "finite_number",
        "is_raw_pdf_raster_space",
                "normalize_blocks",
                "read_layout_pages",
                "render_pdf_pages",
            }

    assert set(extraction.__all__) == expected
    assert all(hasattr(extraction, name) for name in expected)


def test_tagging_consumers_use_the_public_facade() -> None:
    """Application consumers must not couple to tagging implementation modules."""

    consumer_files = (
        SOURCE_ROOT / "ingestion" / "use_cases.py",
        SOURCE_ROOT / "workflows" / "ingest_extracted_document.py",
    )
    implementation_prefixes = (
        "saxophone.tagging.models",
        "saxophone.tagging.parser",
        "saxophone.tagging.ports",
        "saxophone.tagging.use_cases",
    )
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith(implementation_prefixes)
        )
        for path in consumer_files
        if any(
            imported.startswith(implementation_prefixes)
            for imported in _saxophone_imports(path)
        )
    }

    assert violations == {}


def test_tagging_parser_consumes_ingestion_public_facade() -> None:
    """Tagging must consume the stable ingestion contract, not its models module."""

    parser_file = SOURCE_ROOT / "tagging" / "parser.py"
    implementation_prefixes = ("saxophone.ingestion.models",)
    violations = sorted(
        imported
        for imported in _saxophone_imports(parser_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_ingestion_workflow_uses_the_public_facade() -> None:
    """Workflow orchestration must not couple to ingestion implementation modules."""

    workflow_file = SOURCE_ROOT / "workflows" / "ingest_extracted_document.py"
    implementation_prefixes = (
        "saxophone.ingestion.chunking",
        "saxophone.ingestion.models",
        "saxophone.ingestion.ports",
        "saxophone.ingestion.use_cases",
    )
    violations = sorted(
        imported
        for imported in _saxophone_imports(workflow_file)
        if imported.startswith(implementation_prefixes)
    )

    assert violations == []


def test_tagging_exposes_a_public_application_facade() -> None:
    """Consumers should receive tagging contracts and workflows from one module."""

    from saxophone import tagging

    expected = {
        "ExistingTagCandidate",
        "JsonTagCatalogRepository",
        "JsonTaggedParagraphRepository",
        "ParagraphBlock",
        "RemoteParagraphTagger",
        "RemoteTagConflictResolver",
        "TagAndPersistParagraph",
        "TagCatalogRepository",
        "TagConflictResolution",
        "TagConflictResolutionRequest",
        "TagConflictResolver",
        "TagGenerationRequest",
        "TagGenerationResult",
        "TagGenerator",
        "TagParagraph",
        "TagResolution",
        "TaggedParagraph",
        "TaggedParagraphRepository",
        "parse_chunk_paragraphs",
    }

    assert set(tagging.__all__) == expected
    assert all(hasattr(tagging, name) for name in expected)


def test_documents_consumers_use_the_public_facade() -> None:
    """Consumers should not couple to document implementation modules."""

    consumer_files = (
        SOURCE_ROOT / "app" / "factory.py",
        SOURCE_ROOT / "chat" / "ports.py",
        SOURCE_ROOT / "extraction" / "models.py",
        SOURCE_ROOT / "extraction" / "persistence.py",
        SOURCE_ROOT / "extraction" / "remote.py",
        SOURCE_ROOT / "ingestion" / "use_cases.py",
        SOURCE_ROOT / "interfaces" / "api.py",
        SOURCE_ROOT / "platform" / "artifacts.py",
        SOURCE_ROOT / "workflows" / "ingest_extracted_document.py",
        SOURCE_ROOT / "workflows" / "process_document.py",
    )
    implementation_prefixes = (
        "saxophone.documents.knowledge",
        "saxophone.documents.models",
        "saxophone.documents.policies",
        "saxophone.documents.ports",
    )
    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith(implementation_prefixes)
        )
        for path in consumer_files
        if any(
            imported.startswith(implementation_prefixes)
            for imported in _saxophone_imports(path)
        )
    }

    assert violations == {}


def test_documents_exposes_a_public_application_facade() -> None:
    """Consumers should receive document contracts from one stable module."""

    from saxophone import documents

    expected = {
        "ArtifactKind",
        "ArtifactRef",
        "ArtifactRepository",
        "ImageArtifactResolver",
        "KnowledgeChunk",
        "KnowledgeRepository",
        "is_image_media_type",
        "is_safe_artifact_reference",
        "is_safe_document_reference",
        "is_safe_media_type",
        "is_safe_relative_image_reference",
    }

    assert set(documents.__all__) == expected
    assert all(hasattr(documents, name) for name in expected)


def test_documents_facade_does_not_reexport_ingestion_vector_index() -> None:
    """Vector indexing belongs to ingestion, not the document facade."""

    from saxophone import documents

    assert not hasattr(documents, "VectorIndex")
    assert "VectorIndex" not in documents.__all__


def test_ingestion_does_not_depend_on_inbound_framework_or_schemas() -> None:
    """Keep ingestion application code independent from HTTP presentation details."""

    forbidden_roots = {"fastapi", "pydantic"}
    violations: dict[str, list[str]] = {}
    ingestion_root = SOURCE_ROOT / "ingestion"
    for path in ingestion_root.rglob("*.py"):
        forbidden_imports = sorted(_import_roots(path) & forbidden_roots)
        inbound_imports = sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith("saxophone.interfaces")
        )
        if forbidden_imports or inbound_imports:
            violations[str(path.relative_to(SOURCE_ROOT))] = [
                *forbidden_imports,
                *inbound_imports,
            ]

    assert violations == {}


def test_extraction_does_not_depend_on_inbound_framework_or_schemas() -> None:
    """Keep extraction application code independent from HTTP presentation details."""

    forbidden_roots = {"fastapi", "pydantic"}
    violations: dict[str, list[str]] = {}
    extraction_root = SOURCE_ROOT / "extraction"
    for path in extraction_root.rglob("*.py"):
        forbidden_imports = sorted(_import_roots(path) & forbidden_roots)
        inbound_imports = sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith("saxophone.interfaces")
        )
        if forbidden_imports or inbound_imports:
            violations[str(path.relative_to(SOURCE_ROOT))] = [
                *forbidden_imports,
                *inbound_imports,
            ]

    assert violations == {}


def test_chat_does_not_depend_on_inbound_framework_or_schemas() -> None:
    """Keep chat application code independent from HTTP presentation details."""

    forbidden_roots = {"fastapi", "pydantic"}
    violations: dict[str, list[str]] = {}
    chat_root = SOURCE_ROOT / "chat"
    for path in chat_root.rglob("*.py"):
        forbidden_imports = sorted(_import_roots(path) & forbidden_roots)
        inbound_imports = sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith("saxophone.interfaces")
        )
        if forbidden_imports or inbound_imports:
            violations[str(path.relative_to(SOURCE_ROOT))] = [
                *forbidden_imports,
                *inbound_imports,
            ]

    assert violations == {}


def test_tagging_does_not_depend_on_inbound_framework_or_schemas() -> None:
    """Keep tagging application code independent from HTTP presentation details."""

    forbidden_roots = {"fastapi", "pydantic"}
    violations: dict[str, list[str]] = {}
    tagging_root = SOURCE_ROOT / "tagging"
    for path in tagging_root.rglob("*.py"):
        forbidden_imports = sorted(_import_roots(path) & forbidden_roots)
        inbound_imports = sorted(
            imported
            for imported in _saxophone_imports(path)
            if imported.startswith("saxophone.interfaces")
        )
        if forbidden_imports or inbound_imports:
            violations[str(path.relative_to(SOURCE_ROOT))] = [
                *forbidden_imports,
                *inbound_imports,
            ]

    assert violations == {}


def test_task_adapters_use_the_litellm_model_client_boundary() -> None:
    """Remote task adapters must not grow their own provider transport."""

    task_adapter_files = (
        SOURCE_ROOT / "chat" / "remote_answer.py",
        SOURCE_ROOT / "extraction" / "remote.py",
        SOURCE_ROOT / "ingestion" / "adapters.py",
        SOURCE_ROOT / "tagging" / "adapters.py",
    )
    violations = {
        str(path.relative_to(SOURCE_ROOT)): {
            "missing_model_client": "saxophone.platform.model_client" not in _saxophone_imports(path),
            "direct_transport": sorted(_import_roots(path) & {"httpx", "openai"}),
        }
        for path in task_adapter_files
        if "saxophone.platform.model_client" not in _saxophone_imports(path)
        or _import_roots(path) & {"httpx", "openai"}
    }

    assert violations == {}


def test_http_transport_is_confined_to_platform_and_composition_root() -> None:
    """Feature modules receive the model port instead of importing HTTP clients."""

    violations = {
        str(path.relative_to(SOURCE_ROOT)): sorted(_import_roots(path) & {"httpx"})
        for path in SOURCE_ROOT.rglob("*.py")
        if _import_roots(path) & {"httpx"}
        and path.relative_to(SOURCE_ROOT).parts[0] not in {"platform", "app"}
    }

    assert violations == {}

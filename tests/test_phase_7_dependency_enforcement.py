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
LEGACY_COMPATIBILITY_FILES = frozenset({"retrieval/adapters.py"})


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

    compatibility_path = SOURCE_ROOT / "retrieval" / "adapters.py"
    assert _import_roots(compatibility_path) & LEGACY_MODULE_ROOTS == {"music_rag"}


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

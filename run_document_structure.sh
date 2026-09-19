#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s nullglob

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UV_BIN="${UV_BIN:-uv}"
BATCH_SIZE="${DOCUMENT_STRUCTURE_BATCH_SIZE:-20}"
ESTIMATE_ONLY=0
INPUTS=()

# Used only when --input is omitted. Edit this list if you want a different
# default batch. Each entry may be an extraction directory or a Markdown file.
DEFAULT_INPUTS=(
  "$PROJECT_DIR/output_v3/Robert A. Luckey, Ph.D. - Saxophone Altissimo"
  "$PROJECT_DIR/output_v3/Technique of the Saxophone Vol 1 - Scale Studies"
)

usage() {
  cat <<'EOF'
Build DeepSeek-repaired document hierarchy for one or more extracted books.

Usage:
  ./run_document_structure.sh [options]

Options:
  --input PATH       Extraction directory or Markdown file; repeat as needed.
                     If omitted, DEFAULT_INPUTS in this script is used.
  --estimate-only    Print token/cost estimates; do not call DeepSeek or write
                     structured outputs.
  --batch-size N     Heading candidates per DeepSeek request (default: 20).
  -h, --help         Show this help.

Actual runs load DEEPSEEK_API_KEY from .env and resume from
document-structure-labels.json when interrupted.
EOF
}

while (($#)); do
  case "$1" in
    --input)
      [[ $# -ge 2 ]] || { echo "Missing value for --input" >&2; exit 2; }
      INPUTS+=("$2")
      shift 2
      ;;
    --estimate-only)
      ESTIMATE_ONLY=1
      shift
      ;;
    --batch-size)
      [[ $# -ge 2 ]] || { echo "Missing value for --batch-size" >&2; exit 2; }
      BATCH_SIZE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v "$UV_BIN" >/dev/null 2>&1 || { echo "uv not found: $UV_BIN" >&2; exit 1; }
[[ "$BATCH_SIZE" =~ ^[1-9][0-9]*$ ]] || { echo "--batch-size must be a positive integer" >&2; exit 2; }
if ((${#INPUTS[@]} == 0)); then
  INPUTS=("${DEFAULT_INPUTS[@]}")
fi

resolve_input() {
  local supplied="$1"
  local candidate
  if [[ "$supplied" = /* ]]; then
    candidate="$supplied"
  else
    candidate="$PROJECT_DIR/$supplied"
  fi

  if [[ -f "$candidate" && "$candidate" == *.md ]]; then
    markdown="$candidate"
    extraction_dir="$(dirname -- "$markdown")"
    return
  fi
  if [[ -d "$candidate" ]]; then
    extraction_dir="$candidate"
    local preferred="$extraction_dir/$(basename -- "$extraction_dir").md"
    if [[ -f "$preferred" ]]; then
      markdown="$preferred"
      return
    fi
    local markdown_candidates=("$extraction_dir"/*.md)
    # Do not accidentally select a generated Markdown file on a repeat run.
    local source_candidates=()
    local item
    for item in "${markdown_candidates[@]}"; do
      [[ "$item" == *-structured.md || "$item" == *-header-chunks.md ]] || source_candidates+=("$item")
    done
    if ((${#source_candidates[@]} == 1)); then
      markdown="${source_candidates[0]}"
      return
    fi
    echo "Expected exactly one source Markdown file in: $extraction_dir" >&2
    return 1
  fi
  echo "Input must be an extraction directory or Markdown file: $supplied" >&2
  return 1
}

run_module() {
  (cd "$PROJECT_DIR" && "$UV_BIN" run python -m "$@")
}

archive_mismatched_structure() {
  local labels_file="$extraction_dir/document-structure-labels.json"
  [[ -f "$labels_file" ]] || return 0

  local current_hash cached_hash archive_dir item
  current_hash="$(sha256sum "$markdown")"
  current_hash="${current_hash%% *}"
  cached_hash="$(cd "$PROJECT_DIR" && "$UV_BIN" run python -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("source_sha256", ""))' "$labels_file")"
  [[ -n "$cached_hash" && "$cached_hash" != "$current_hash" ]] || return 0

  archive_dir="$extraction_dir/structure-archive/source-${cached_hash:0:12}"
  if [[ -e "$archive_dir" ]]; then
    archive_dir="$archive_dir-$(date +%Y%m%dT%H%M%S)"
  fi
  mkdir -p "$archive_dir"
  for item in \
    document-structure-labels.json \
    document-structure-run.json \
    document-structure.json \
    document-structured-chunks.json \
    document-structured.md; do
    if [[ -e "$extraction_dir/$item" ]]; then
      mv "$extraction_dir/$item" "$archive_dir/$item"
    fi
  done
  echo "  Archived structure from a different source: $archive_dir"
}

echo "Inputs: ${#INPUTS[@]} | batch_size=$BATCH_SIZE | estimate_only=$ESTIMATE_ONLY"
input_number=0
for supplied_input in "${INPUTS[@]}"; do
  input_number=$((input_number + 1))
  resolve_input "$supplied_input"
  echo
  echo "[$input_number/${#INPUTS[@]}] $markdown"

  # Estimate mode is read-only. On an actual run, preserve stale outputs from
  # another Markdown source before creating a fresh resumable cache.
  if ((!ESTIMATE_ONLY)); then
    archive_mismatched_structure
  fi

  args=(
    extracted.structure_markdown_with_llm
    "$markdown"
    --batch-size "$BATCH_SIZE"
  )
  if ((ESTIMATE_ONLY)); then
    args+=(--estimate-only)
  else
    args+=(
      --labels-output "$extraction_dir/document-structure-labels.json"
      --structure-output "$extraction_dir/document-structure.json"
      --json-output "$extraction_dir/document-structured-chunks.json"
      --markdown-output "$extraction_dir/document-structured.md"
      --run-output "$extraction_dir/document-structure-run.json"
    )
    if [[ -d "$extraction_dir/layout" ]]; then
      args+=(--layout-dir "$extraction_dir/layout")
    fi
    if [[ -f "$extraction_dir/vlm-figures/figure-vlm-results.jsonl" ]]; then
      args+=(--vlm-results "$extraction_dir/vlm-figures/figure-vlm-results.jsonl")
    fi
  fi
  run_module "${args[@]}"
done

echo
if ((ESTIMATE_ONLY)); then
  echo "Finished estimates. No API requests were made."
else
  echo "Finished document structure generation for all requested inputs."
fi

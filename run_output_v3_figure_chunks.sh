#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s nullglob

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_ROOT="$PROJECT_DIR/output_v3"
UV_BIN="${UV_BIN:-uv}"
WORKERS="${FIGURE_VLM_WORKERS:-4}"
HEADING_LEVEL=2
PLAN_ONLY=0
FORCE=0
MAX_FIGURES=""
INPUTS=()

# Default inputs used when no --input argument is supplied. You may edit this
# list directly; each item may also be replaced at runtime with --input.
DEFAULT_INPUTS=(
  "$OUTPUT_ROOT/Music Theory For Dummies"
  "$OUTPUT_ROOT/Robert A. Luckey, Ph.D. - Saxophone Altissimo"
  "$OUTPUT_ROOT/Technique of the Saxophone Vol 1 - Scale Studies"
)

usage() {
  cat <<'EOF'
Run figure caption mapping, DeepSeek Vision enrichment, figure review, and
header chunk generation for one or more PaddleOCR extraction inputs.

Usage:
  ./run_output_v3_figure_chunks.sh [options]

Options:
  --input PATH         Extraction directory or its Markdown file. Repeat this
                       option to process multiple inputs. If omitted, the three
                       entries in DEFAULT_INPUTS are processed.
  --plan-only          Build caption maps and VLM request plans; do not call API.
  --workers N          Concurrent DeepSeek requests (default: 4 or FIGURE_VLM_WORKERS).
  --max-figures N      Process at most N pending figures per book (smoke test).
  --heading-level N    Markdown heading level used for chunks (default: 2).
  --force              Re-run figures already marked completed.
  -h, --help           Show this help.

The normal run loads DEEPSEEK_API_KEY from .env. VLM JSONL output is resumable.
EOF
}

while (($#)); do
  case "$1" in
    --input)
      [[ $# -ge 2 ]] || { echo "Missing value for --input" >&2; exit 2; }
      INPUTS+=("$2")
      shift 2
      ;;
    --plan-only)
      PLAN_ONLY=1
      shift
      ;;
    --workers)
      [[ $# -ge 2 ]] || { echo "Missing value for --workers" >&2; exit 2; }
      WORKERS="$2"
      shift 2
      ;;
    --max-figures)
      [[ $# -ge 2 ]] || { echo "Missing value for --max-figures" >&2; exit 2; }
      MAX_FIGURES="$2"
      shift 2
      ;;
    --heading-level)
      [[ $# -ge 2 ]] || { echo "Missing value for --heading-level" >&2; exit 2; }
      HEADING_LEVEL="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
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
[[ "$WORKERS" =~ ^[1-9][0-9]*$ ]] || { echo "--workers must be a positive integer" >&2; exit 2; }
[[ "$HEADING_LEVEL" =~ ^[1-6]$ ]] || { echo "--heading-level must be between 1 and 6" >&2; exit 2; }
if [[ -n "$MAX_FIGURES" && ! "$MAX_FIGURES" =~ ^[1-9][0-9]*$ ]]; then
  echo "--max-figures must be a positive integer" >&2
  exit 2
fi

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

  if [[ -d "$candidate" ]]; then
    extraction_dir="$candidate"
    markdown="$extraction_dir/$(basename -- "$extraction_dir").md"
    if [[ ! -f "$markdown" ]]; then
      local markdown_candidates=("$extraction_dir"/*.md)
      if ((${#markdown_candidates[@]} != 1)); then
        echo "Expected exactly one Markdown file in: $extraction_dir" >&2
        return 1
      fi
      markdown="${markdown_candidates[0]}"
    fi
    return
  fi

  if [[ -f "$candidate" && "$candidate" == *.md ]]; then
    markdown="$candidate"
    extraction_dir="$(dirname -- "$markdown")"
    return
  fi

  echo "Input must be an extraction directory or Markdown file: $supplied" >&2
  return 1
}

run_module() {
  (cd "$PROJECT_DIR" && "$UV_BIN" run python -m "$@")
}

echo "Output root: $OUTPUT_ROOT"
echo "Inputs: ${#INPUTS[@]} | workers=$WORKERS | heading_level=$HEADING_LEVEL"

book_number=0
for supplied_input in "${INPUTS[@]}"; do
  book_number=$((book_number + 1))
  resolve_input "$supplied_input"
  book="$(basename -- "$markdown" .md)"
  results="$extraction_dir/vlm-figures/figure-vlm-results.jsonl"

  [[ -d "$extraction_dir/layout" ]] || { echo "Missing layout directory: $extraction_dir/layout" >&2; exit 1; }
  [[ -d "$extraction_dir/imgs" || -d "$extraction_dir/images" ]] || {
    echo "Missing imgs/ or images/ directory in: $extraction_dir" >&2
    exit 1
  }
  [[ -f "$markdown" ]] || { echo "Missing Markdown: $markdown" >&2; exit 1; }

  echo
  echo "[$book_number/${#INPUTS[@]}] $book"
  echo "  Input: $markdown"
  echo "  [1/4] Mapping image crops to heuristic captions"
  run_module extracted.map_paddle_vl_captions "$extraction_dir"

  echo "  [2/4] DeepSeek Flash Vision enrichment"
  analyze_args=(extracted.analyze_paddle_vl_figures "$extraction_dir" --workers "$WORKERS")
  ((PLAN_ONLY)) && analyze_args+=(--plan-only)
  ((FORCE)) && analyze_args+=(--force)
  [[ -n "$MAX_FIGURES" ]] && analyze_args+=(--max-figures "$MAX_FIGURES")
  run_module "${analyze_args[@]}"

  if ((PLAN_ONLY)); then
    echo "  Plan written; review/chunk steps skipped because no API result was requested."
    continue
  fi

  echo "  [3/4] Rendering valid figures with captions"
  run_module extracted.render_vlm_figures_markdown "$extraction_dir" --only-valid

  echo "  [4/4] Building header chunks and inserting valid figure captions"
  run_module extracted.extract_header_chunks \
    "$markdown" \
    --heading-level "$HEADING_LEVEL" \
    --vlm-results "$results"
done

echo
if ((PLAN_ONLY)); then
  echo "Finished planning all requested inputs. No DeepSeek API requests were made."
else
  echo "Finished figure enrichment and header chunks for all requested inputs."
  echo "Note: legacy output_v3 Markdown has no '## Page N' markers, so generated"
  echo "chunk page_start/page_end fields are null; header content and figures remain available."
fi

#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
source_md="$repo_root/Hausarbeit.md"
content_md="$script_dir/Hausarbeit-content.md"
build_dir="$repo_root/tmp/pdfs/hausarbeit"
texmf_var="$build_dir/texmf-var"
texmf_cache="$build_dir/texmf-cache"

mkdir -p "$build_dir" "$texmf_var" "$texmf_cache"
export TEXMFVAR="$texmf_var"
export TEXMFCACHE="$texmf_cache"

# Remove the Markdown-only title and hand-written table of contents. LaTeX
# supplies both. Heading numbers are also removed because LaTeX adds them.
awk '
  BEGIN { emit = 0 }
  /^## 1\. Einleitung[[:space:]]*$/ { emit = 1 }
  emit {
    if ($0 ~ /^#### [0-9]+\.[0-9]+\.[0-9]+[[:space:]]+/) {
      sub(/^#### [0-9]+\.[0-9]+\.[0-9]+[[:space:]]+/, "#### ")
    } else if ($0 ~ /^### [0-9]+\.[0-9]+[[:space:]]+/) {
      sub(/^### [0-9]+\.[0-9]+[[:space:]]+/, "### ")
    } else if ($0 ~ /^## [0-9]+\.[[:space:]]+/) {
      sub(/^## [0-9]+\.[[:space:]]+/, "## ")
    }
    print
  }
' "$source_md" > "$content_md"

cd "$script_dir"
latexmk \
  -g \
  -lualatex \
  -shell-escape \
  -interaction=nonstopmode \
  -halt-on-error \
  -file-line-error \
  -outdir="$build_dir" \
  Hausarbeit.tex

cp "$build_dir/Hausarbeit.pdf" "$script_dir/Hausarbeit.pdf"

#!/usr/bin/env bash
# Build .skill bundles from the tracked sources in this directory.
#
# The .skill file is a zip and therefore a build artifact, not source. Keeping
# only the zip in the repo means edits have no diff and no history — which is
# how a change to a skill becomes unreviewable and unrevertable. Sources are
# tracked; the bundles are generated and gitignored.
#
#   ./skills/build.sh          -> writes ../<name>.skill for each skill
#   ./skills/build.sh /tmp/out -> writes into a chosen directory
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-..}"
mkdir -p "$OUT"
for dir in */; do
  name="${dir%/}"
  [ -f "$name/SKILL.md" ] || continue
  target="$OUT/$name.skill"
  rm -f "$target"
  zip -q -r -X "$target" "$name" -x '*/__pycache__/*' '*.pyc'
  # A bundle whose frontmatter is malformed installs but never triggers.
  python3 - "$name/SKILL.md" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
assert m, f"{sys.argv[1]}: missing YAML frontmatter"
for key in ("name:", "description:"):
    assert key in m.group(1), f"{sys.argv[1]}: frontmatter missing {key}"
PY
  unzip -t -q "$target"
  printf '  built %-34s %s\n' "$name.skill" "$(du -h "$target" | cut -f1)"
done

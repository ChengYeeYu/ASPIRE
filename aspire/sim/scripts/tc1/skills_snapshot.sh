#!/bin/bash
### Freeze / restore the shared LIBERO skill library between comparison runs ###
#   bash scripts/tc1/skills_snapshot.sh save    <name>   # copy .claude/libero/skills -> outputs/skill_snapshots/<name>
#   bash scripts/tc1/skills_snapshot.sh restore <name>   # make .claude/libero/skills identical to the snapshot
#   bash scripts/tc1/skills_snapshot.sh check   <name>   # exit 1 (and show the diff) if the library changed
# Tiny file ops -- fine on the head node. Run from ~/ASPIRE/aspire/sim.
set -euo pipefail

cmd="${1:?usage: skills_snapshot.sh save|restore|check <name>}"
name="${2:?snapshot name, e.g. after_fixloop}"
skills=".claude/libero/skills"
snap="outputs/skill_snapshots/$name"
[[ -d "$skills" ]] || { echo "run from aspire/sim (no $skills here)"; exit 1; }

case "$cmd" in
  save)
    [[ -e "$snap" ]] && { echo "snapshot exists, refusing to overwrite: $snap"; exit 1; }
    mkdir -p "$snap"
    cp -a "$skills/." "$snap/"
    (cd "$snap" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
    echo "saved $skills -> $snap ($(wc -l < "$snap/SHA256SUMS") files)"
    ;;
  restore)
    [[ -f "$snap/SHA256SUMS" ]] || { echo "no snapshot: $snap"; exit 1; }
    (cd "$snap" && sha256sum --quiet -c SHA256SUMS) || { echo "snapshot corrupted: $snap"; exit 1; }
    find "$skills" -mindepth 1 -delete
    cp -a "$snap/." "$skills/"
    rm -f "$skills/SHA256SUMS"
    echo "restored $skills from $snap"
    ;;
  check)
    [[ -f "$snap/SHA256SUMS" ]] || { echo "no snapshot: $snap"; exit 1; }
    if diff -r --exclude=SHA256SUMS "$snap" "$skills"; then
      echo "OK: $skills matches $snap"
    else
      echo "CHANGED: $skills differs from $snap (diff above)"; exit 1
    fi
    ;;
  *) echo "unknown command: $cmd"; exit 1 ;;
esac

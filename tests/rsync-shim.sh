#!/usr/bin/env bash
# Minimal rsync stand-in for local test runs on machines without rsync.
# Supports only the flags the update engine actually uses:
#   -a --delete --dry-run --itemize-changes --exclude <pat>  SRC/ DST/
# Semantics: mirror SRC into DST, optionally deleting DST-only files, reporting
# deletions as "*deleting   <relpath>" in dry-run mode.
set -uo pipefail

delete=0; dry=0; excludes=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--archive|--recursive|--times|--perms|--checksum) shift ;;        --delete|--delete-excluded) delete=1; shift ;;
        --dry-run|-n) dry=1; shift ;;
        --itemize-changes|-i) shift ;;
        --exclude) excludes+=("$2"); shift 2 ;;
        --exclude=*) excludes+=("${1#--exclude=}"); shift ;;
        --) shift; break ;;
        -*) shift ;;
        *) break ;;
    esac
done
SRC="${1%/}/"; DST="${2%/}"

excluded() {  # <relpath> -> 0 when the path matches an exclude pattern
    local p="$1" pat base
    base="${p##*/}"
    for pat in "${excludes[@]:-}"; do
        [[ -z "$pat" ]] && continue
        pat="${pat%/}"
        # glob patterns such as *.pyc
        if [[ "$pat" == *'*'* || "$pat" == *'?'* ]]; then
            # shellcheck disable=SC2053
            [[ "$p" == $pat ]] && return 0
            # shellcheck disable=SC2053
            [[ "$base" == $pat ]] && return 0
            continue
        fi
        case "$p" in
            "$pat"|"$pat"/*|*/"$pat"|*/"$pat"/*) return 0 ;;
        esac
    done
    return 1
}

[[ -d "$SRC" ]] || { echo "rsync-shim: no such dir $SRC" >&2; exit 1; }
mkdir -p "$DST" || exit 1

# --- source side ---
src_files=()
while IFS= read -r f; do
    rel="${f#$SRC}"
    excluded "$rel" && continue
    src_files+=("$rel")
done < <(find "$SRC" -type f 2>/dev/null | sort)

for rel in "${src_files[@]:-}"; do
    [[ -z "$rel" ]] && continue
    if [[ ! -f "$DST/$rel" ]] || ! cmp -s "$SRC$rel" "$DST/$rel"; then
        if [[ "$dry" -eq 0 ]]; then
            mkdir -p "$(dirname "$DST/$rel")"
            cp -p "$SRC$rel" "$DST/$rel"
        fi
    fi
done

# --- destination side (deletions) ---
if [[ "$delete" -eq 1 ]]; then
    while IFS= read -r f; do
        rel="${f#$DST/}"
        excluded "$rel" && continue
        keep=0
        for s in "${src_files[@]:-}"; do [[ "$s" == "$rel" ]] && { keep=1; break; }; done
        [[ "$keep" -eq 1 ]] && continue
        if [[ "$dry" -eq 1 ]]; then
            echo "*deleting   $rel"
        else
            rm -f "$f"
        fi
    done < <(find "$DST" -type f 2>/dev/null | sort)
    # drop directories that deletion left empty
    if [[ "$dry" -eq 0 ]]; then
        find "$DST" -mindepth 1 -type d -empty -delete 2>/dev/null || true
    fi
fi
exit 0

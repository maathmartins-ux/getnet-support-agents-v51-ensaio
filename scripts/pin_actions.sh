#!/usr/bin/env bash
# Fixa cada `uses: dono/repo@tag` dos workflows no SHA do commit da tag (tag é móvel: em março/2026 tags de
# actions populares foram reescritas para código malicioso; SHA não muda). A versão fica em comentário, que é
# o que o Dependabot (package-ecosystem: github-actions) lê para propor a próxima.
#
# Uso:
#   scripts/pin_actions.sh            # reescreve .github/workflows/*.yml no lugar
#   scripts/pin_actions.sh --check    # só confere: sai 1 se houver `uses:` sem SHA (o teste offline faz o mesmo)
#
# Resolve via `git ls-remote` (sem token, sem API): tag anotada usa o commit "descascado" (^{}).
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-pin}"
status=0
for wf in .github/workflows/*.yml; do
  while IFS= read -r line; do
    ref="$(sed -E 's/.*uses:[[:space:]]*([^[:space:]#]+).*/\1/' <<<"$line")"
    case "$ref" in ./*|docker://*) continue ;; esac
    repo="${ref%@*}"; tag="${ref#*@}"
    [[ "$tag" =~ ^[0-9a-f]{40}$ ]] && continue
    if [[ "$mode" == "--check" ]]; then
      echo "$wf: sem SHA: $ref"; status=1; continue
    fi
    base="$(cut -d/ -f1-2 <<<"$repo")"   # dono/repo/subpasta@tag → o repositório é dono/repo
    out="$(git ls-remote --tags "https://github.com/$base" "refs/tags/$tag" "refs/tags/$tag^{}")"
    sha="$(awk '/\^\{\}$/ {print $1}' <<<"$out")"
    [[ -n "$sha" ]] || sha="$(awk 'NR==1 {print $1}' <<<"$out")"
    if [[ -z "$sha" ]]; then
      echo "$wf: tag $tag não existe em $base" >&2; status=1; continue
    fi
    echo "$wf: $repo@$tag -> $sha"
    esc_ref="$(sed 's/[.[\*^$/]/\\&/g' <<<"$ref")"
    sed -i -E "s/uses:([[:space:]]*)${esc_ref}([[:space:]]*#.*)?$/uses:\1${repo//\//\\/}@${sha} # ${tag}/" "$wf"
  done < <(grep -E '^[[:space:]]*-?[[:space:]]*uses:' "$wf")
done
exit "$status"

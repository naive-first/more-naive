#!/usr/bin/env bash
set -euo pipefail
fail() { echo "$1" >&2; exit 2; }
[[ ${GITHUB_REPOSITORY-} == naive-first/more-naive && ${GITHUB_REF-} == refs/heads/main ]] || fail 'promotion requires trusted repository main'
[[ ${IMAGE_DIGEST-} =~ ^sha256:[0-9a-f]{64}$ && ${SOURCE_SHA-} =~ ^[0-9a-f]{40}$ ]] || fail 'full image digest and source commit SHA required'
export IMAGE=ghcr.io/naive-first/more-naive-backend
values=infra/environments/prod/backend.yaml
application=infra/argocd/applications/prod/backend.yaml
umask 077
temporary=$(mktemp -d); trap 'rm -rf "$temporary"' EXIT
mkdir "$temporary/docker"
printf '{"auths":{}}\n' > "$temporary/docker/config.json"
reference="$IMAGE@$IMAGE_DIGEST"
for operation in pull inspect; do
  command=(docker --config "$temporary/docker")
  if [[ $operation == pull ]]; then command+=(pull "$reference"); else command+=(image inspect "$reference" --format '{{json .RepoDigests}}'); fi
  if "${command[@]}" > "$temporary/stdout" 2> "$temporary/stderr"; then code=0; else code=$?; fi
  {
    printf '$'; printf ' %q' "${command[@]}"; printf '\n[stdout]\n'; cat "$temporary/stdout"
    printf '\n[stderr]\n'; cat "$temporary/stderr"; printf '\n[exit=%s]\n' "$code"
  } >> "$temporary/proof"
  [[ $code == 0 ]] || { cat "$temporary/proof"; fail 'anonymous pull failed; verify Public visibility before rerunning'; }
done
cat "$temporary/proof"
jq -e --arg reference "$reference" 'index($reference) != null' "$temporary/stdout" >/dev/null || fail 'pulled image digest mismatch'
remote=$(git remote get-url origin)
git init -q "$temporary/repository"
git=(git -C "$temporary/repository" -c credential.helper= -c 'credential.helper=!gh auth git-credential')
"${git[@]}" remote add origin "$remote"
"${git[@]}" fetch --quiet origin refs/heads/main
base=$("${git[@]}" rev-parse FETCH_HEAD)
"${git[@]}" checkout --quiet -b promotion "$base"
file="$temporary/repository/$values"
[[ -f $file ]] || fail 'deployment values prerequisite missing'
yq -e '[keys | .[] | select(. == "image")] | length == 1' "$file" >/dev/null || fail 'one image mapping required'
for field in repository digest; do
  FIELD="$field" yq -e '[.image | keys | .[] | select(. == strenv(FIELD))] | length == 1' "$file" >/dev/null || fail 'one image repository and digest required'
done
yq -e '.image.repository == strenv(IMAGE)' "$file" >/dev/null || fail 'approved image repository required'
active=false; pending=false
[[ ! -f $temporary/repository/$application ]] || active=true
[[ ! -f $temporary/repository/$application.example ]] || pending=true
[[ $active != "$pending" ]] || fail 'exactly one active or pending backend Application required'
if [[ $active == true && $(yq '.image.digest' "$file") == "$IMAGE_DIGEST" ]]; then echo 'Already promoted: main has verified digest and active Application'; exit 0; fi
yq -i '.image.digest = strenv(IMAGE_DIGEST)' "$file"
if $pending; then mv "$temporary/repository/$application.example" "$temporary/repository/$application"; fi
"${git[@]}" add -A -- "$values" "$(dirname "$application")"
expected_tree=$("${git[@]}" write-tree)
branch="ci/backend-${SOURCE_SHA:0:12}-${IMAGE_DIGEST:7:12}-${base:0:7}"
if "${git[@]}" ls-remote --exit-code origin "refs/heads/$branch" > /dev/null; then
  "${git[@]}" fetch --quiet origin "refs/heads/$branch"
  [[ $("${git[@]}" rev-parse 'FETCH_HEAD^{tree}') == "$expected_tree" ]] || fail 'existing promotion branch differs; refusing overwrite'
else
  code=$?; [[ $code == 2 ]] || fail 'could not inspect promotion branch'
  "${git[@]}" -c user.name=github-actions\[bot\] -c user.email=41898282+github-actions\[bot\]@users.noreply.github.com commit --quiet -m "chore(deploy): backend image $IMAGE_DIGEST"
  "${git[@]}" push origin "HEAD:refs/heads/$branch"
fi
url=$(gh pr list --repo "$GITHUB_REPOSITORY" --base main --head "$branch" --state open --json url --jq '.[0].url // empty')
if [[ -z $url ]]; then
  fence=$(awk '{while(match($0,/`+/)){if(RLENGTH>max)max=RLENGTH;$0=substr($0,RSTART+RLENGTH)}} END{for(i=0;i<max+4;i++)printf "`"}' "$temporary/proof")
  {
    printf 'Promote public image `%s`.\n\nSource: [%s](https://github.com/%s/commit/%s).\n\n' "$reference" "$SOURCE_SHA" "$GITHUB_REPOSITORY" "$SOURCE_SHA"
    printf 'Anonymous pull evidence (raw):\n\n%stext\n' "$fence"; cat "$temporary/proof"; printf '%s\n\n' "$fence"
    printf 'Updates only the verified image digest and activates the pending Application on first promotion. Normal review and merge are required.\n'
  } > "$temporary/body"
  url=$(gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$branch" --title "chore(deploy): backend ${IMAGE_DIGEST:7:12}" --body-file "$temporary/body")
fi
printf '%s\n' "$url"
if [[ -n ${GITHUB_STEP_SUMMARY-} ]]; then printf 'Public backend image: `%s`\n\n%s\n' "$reference" "$url" >> "$GITHUB_STEP_SUMMARY"; fi

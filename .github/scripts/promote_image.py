"""익명 pull이 확인된 이미지의 prod 설정 PR만 생성한다."""

import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'naive-first/more-naive'
IMAGE = 'ghcr.io/naive-first/more-naive-backend'
VALUES = 'infra/environments/prod/backend.yaml'
APPLICATION = 'infra/argocd/applications/prod/backend.yaml'


def validate(digest, source):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('Expected a full sha256 image digest')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('Expected a full source commit SHA')


def update_digest(text, digest):
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == 'image:' and not line.startswith(' ')]
    if len(starts) != 1:
        raise ValueError('Expected one top-level image mapping')
    start = starts[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].strip() and not lines[i].startswith((' ', '#'))), len(lines))
    repositories = [line for line in lines[start:end] if re.match(r'^  repository:', line)]
    digests = [i for i in range(start, end) if re.match(r'^  digest:', lines[i])]
    if len(repositories) != 1 or repositories[0].split(':', 1)[1].strip().strip('\"\'') != IMAGE or len(digests) != 1:
        raise ValueError('Expected the approved image.repository and one image.digest')
    lines[digests[0]] = f'  digest: "{digest}"\n'
    return ''.join(lines)


def verify_public_image(digest):
    proof = ''
    with tempfile.TemporaryDirectory(prefix='ghcr-anonymous-') as directory:
        Path(directory, 'config.json').write_text('{"auths":{}}\n')
        reference = f'{IMAGE}@{digest}'
        commands = [
            ['docker', '--config', directory, 'pull', reference],
            ['docker', '--config', directory, 'image', 'inspect', reference, '--format', '{{json .RepoDigests}}'],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
            raw = f'$ {shlex.join(command)}\n{result.stdout}{result.stderr}\n[exit={result.returncode}]\n'
            print(raw, end='', flush=True)
            proof += raw
            if result.returncode:
                raise RuntimeError('Anonymous pull failed; package administrator must verify Public visibility, then rerun the workflow')
        if reference not in json.loads(result.stdout):
            raise RuntimeError('Pulled image does not match the requested digest')
    return proof


class GitHub:
    def __init__(self, token):
        self.token = token

    def call(self, method, endpoint, payload=None, optional=False):
        request = urllib.request.Request(
            f'https://api.github.com/repos/{REPOSITORY}/{endpoint}',
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if optional and error.code == 404:
                return None
            raise RuntimeError(f'GitHub {method} {endpoint} failed with HTTP {error.code}; check repository Actions PR permissions') from error

    def read(self, path, ref, optional=False):
        result = self.call('GET', f'contents/{path}?{urllib.parse.urlencode({"ref": ref})}', optional=optional)
        return None if result is None else base64.b64decode(result['content']).decode()


def create_pull_request(api, digest, source, proof):
    base = api.call('GET', 'git/ref/heads/main')['object']['sha']
    values = api.read(VALUES, base)
    updated = update_digest(values, digest)
    active = api.read(APPLICATION, base, optional=True)
    example = api.read(APPLICATION + '.example', base, optional=True)
    if (active is None) == (example is None):
        raise ValueError('Expected exactly one active or pending backend Application from deployment setup')
    if values == updated and active is not None:
        return 'Already promoted: main has the verified digest and active Application'
    branch = f'ci/backend-{source[:12]}-{digest[7:19]}-{base[:7]}'
    existing = api.call('GET', 'git/ref/heads/' + branch, optional=True)
    if existing is None:
        tree = api.call('GET', 'git/commits/' + base)['tree']['sha']
        changes = [{'path': VALUES, 'mode': '100644', 'type': 'blob', 'content': updated}]
        if example is not None:
            changes.extend([
                {'path': APPLICATION + '.example', 'mode': '100644', 'type': 'blob', 'sha': None},
                {'path': APPLICATION, 'mode': '100644', 'type': 'blob', 'content': example},
            ])
        tree = api.call('POST', 'git/trees', {'base_tree': tree, 'tree': changes})['sha']
        commit = api.call('POST', 'git/commits', {'message': f'chore(deploy): backend image {digest}', 'tree': tree, 'parents': [base]})['sha']
        api.call('POST', 'git/refs', {'ref': 'refs/heads/' + branch, 'sha': commit})
    else:
        ref = existing['object']['sha']
        if api.read(VALUES, ref) != updated or api.read(APPLICATION, ref, optional=True) is None:
            raise ValueError('Existing promotion branch differs; refusing to overwrite it')
    query = urllib.parse.urlencode({'head': f'naive-first:{branch}', 'base': 'main', 'state': 'open'})
    prs = api.call('GET', 'pulls?' + query)
    if prs:
        return prs[0]['html_url']
    fence = '`' * (max((len(match) for match in re.findall(r'`+', proof)), default=3) + 1)
    body = (f'Promote public image `{IMAGE}@{digest}`.\n\nSource commit: '
            f'[{source}](https://github.com/{REPOSITORY}/commit/{source}).\n\n'
            f'Anonymous pull evidence (raw):\n\n{fence}text\n{proof}{fence}\n\n'
            'This PR changes only the verified image digest and, on first promotion, activates the pending backend Application. '
            'Merge requires normal review; CI does not access the cluster or merge this PR.')
    return api.call('POST', 'pulls', {'title': f'chore(deploy): backend {digest[7:19]}',
                    'head': branch, 'base': 'main', 'body': body})['html_url']


def promote(api, digest, source):
    validate(digest, source)
    proof = verify_public_image(digest)
    return create_pull_request(api, digest, source, proof)


if __name__ == '__main__':
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('Promotion runs only for the trusted repository main branch')
    result = promote(GitHub(os.environ['GH_TOKEN']), os.environ['IMAGE_DIGEST'], os.environ['SOURCE_SHA'])
    print(result)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(f'Public backend image: `{IMAGE}@{os.environ["IMAGE_DIGEST"]}`\n\n{result}\n')

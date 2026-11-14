import unittest
from unittest.mock import Mock, patch

import promote_image as promotion

DIGEST = 'sha256:' + 'a' * 64
SOURCE = 'b' * 40
VALUES = f'image:\n  repository: {promotion.IMAGE}\n  digest: ""\nreplicaCount: 1\n'


class FakeGitHub:
    def __init__(self, active=False, missing=False, values=VALUES):
        self.active = active
        self.missing = missing
        self.values = values
        self.writes = []

    def read(self, path, ref, optional=False):
        if path == promotion.VALUES:
            return self.values
        if self.missing:
            return None
        if path == promotion.APPLICATION and self.active:
            return 'kind: Application\n'
        if path == promotion.APPLICATION + '.example' and not self.active:
            return 'kind: Application\n'
        return None

    def call(self, method, endpoint, payload=None, optional=False):
        if method == 'POST':
            self.writes.append((endpoint, payload))
            return {'html_url': 'https://github.com/naive-first/more-naive/pull/999', 'sha': 'c' * 40}
        if endpoint == 'git/ref/heads/main':
            return {'object': {'sha': 'd' * 40}}
        if endpoint.startswith('git/ref/heads/'):
            return None
        if endpoint.startswith('git/commits/'):
            return {'tree': {'sha': 'e' * 40}}
        if endpoint.startswith('pulls?'):
            return []
        raise AssertionError(endpoint)


class PromotionTest(unittest.TestCase):
    def test_only_image_digest_changes(self):
        updated = promotion.update_digest(VALUES, DIGEST)
        self.assertEqual(updated, VALUES.replace('digest: ""', f'digest: "{DIGEST}"'))

    def test_unknown_repository_or_duplicate_digest_is_rejected(self):
        for value in [VALUES.replace(promotion.IMAGE, 'ghcr.io/unapproved/image'), VALUES.replace('  digest:', '  digest: "old"\n  digest:')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                promotion.update_digest(value, DIGEST)

    def test_invalid_digest_or_source_stops_before_pull_or_api(self):
        api = Mock()
        with patch.object(promotion, 'verify_public_image') as pull:
            for digest, source in [('latest', SOURCE), (DIGEST, 'main'), ('sha256:' + '0' * 63, SOURCE)]:
                with self.subTest(digest=digest), self.assertRaises(ValueError):
                    promotion.promote(api, digest, source)
            pull.assert_not_called()
        api.call.assert_not_called()

    def test_private_image_failure_stops_before_any_configuration_api(self):
        api = Mock()
        with patch.object(promotion, 'verify_public_image', side_effect=RuntimeError('anonymous pull denied')):
            with self.assertRaises(RuntimeError):
                promotion.promote(api, DIGEST, SOURCE)
        api.call.assert_not_called()
        api.read.assert_not_called()

    def test_first_promotion_atomically_sets_digest_and_activates_application(self):
        api = FakeGitHub()
        with patch.object(promotion, 'verify_public_image', return_value='raw anonymous pull stdout\n[exit=0]\n'):
            result = promotion.promote(api, DIGEST, SOURCE)
        changes = next(payload['tree'] for endpoint, payload in api.writes if endpoint == 'git/trees')
        self.assertEqual({entry['path'] for entry in changes}, {promotion.VALUES, promotion.APPLICATION, promotion.APPLICATION + '.example'})
        self.assertEqual(next(entry['sha'] for entry in changes if entry['path'].endswith('.example')), None)
        self.assertIn(DIGEST, next(entry['content'] for entry in changes if entry['path'] == promotion.VALUES))
        body = next(payload['body'] for endpoint, payload in api.writes if endpoint == 'pulls')
        self.assertIn('raw anonymous pull stdout\n[exit=0]\n', body)
        self.assertIn(SOURCE, body)
        self.assertIn(DIGEST, body)
        self.assertNotIn('closes #', body)
        self.assertTrue(result.endswith('/999'))

    def test_later_promotion_only_changes_values(self):
        api = FakeGitHub(active=True)
        promotion.create_pull_request(api, DIGEST, SOURCE, 'verified')
        changes = next(payload['tree'] for endpoint, payload in api.writes if endpoint == 'git/trees')
        self.assertEqual([entry['path'] for entry in changes], [promotion.VALUES])

    def test_missing_deployment_prerequisite_does_not_create_a_branch(self):
        api = FakeGitHub(missing=True)
        with self.assertRaises(ValueError):
            promotion.create_pull_request(api, DIGEST, SOURCE, 'verified')
        self.assertEqual(api.writes, [])

    def test_same_active_digest_is_idempotent(self):
        api = FakeGitHub(active=True, values=promotion.update_digest(VALUES, DIGEST))
        self.assertTrue(promotion.create_pull_request(api, DIGEST, SOURCE, 'verified').startswith('Already promoted'))
        self.assertEqual(api.writes, [])


if __name__ == '__main__':
    unittest.main()

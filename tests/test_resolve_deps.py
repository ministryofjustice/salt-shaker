import os
import unittest
import responses
import yaml
import json

from mock import patch


from shaker import resolve_deps


class ResolveDepsTest(unittest.TestCase):

    def setUp(self):
        os.environ['GITHUB_TOKEN'] = 'fake'

    @responses.activate
    def test_get_tags(self):
        json_resp = [
            {
                "name": "v0.1",
                "commit": {
                    "sha": "c5b97d5ae6c19d5c5df71a34c7fbeeda2479ccbc",
                    "url": "https://api.github.com/repos/octocat/Hello-World/commits/c5b97d5ae6c19d5c5df71a34c7fbeeda2479ccbc"
                },
                "zipball_url": "https://github.com/octocat/Hello-World/zipball/v0.1",
                "tarball_url": "https://github.com/octocat/Hello-World/tarball/v0.1"
            },
            {
                "name": "v1.1",
                "commit": {
                    "sha": "fake",
                    "url": "https://api.github.com/repos/octocat/Hello-World/commits/fake"
                },
                "zipball_url": "https://github.com/octocat/Hello-World/zipball/v1.1",
                "tarball_url": "https://github.com/octocat/Hello-World/tarball/v1.1"
            }
        ]

        responses.add(
            responses.GET,
            "https://api.github.com/repos/ministryofjustice/simple-formula/tags",
            content_type="application/json",
            body=json.dumps(json_resp)
        )

        got = resolve_deps.get_tags("ministryofjustice", "simple-formula")
        latest_tag = 'v1.1'
        all_vers = ['0.1', '1.1']
        self.assertEqual((latest_tag, all_vers), got)

    @patch.object(resolve_deps, 'get_tags')
    def test_check_constraint_none(self, mock_get_tags):
        mock_get_tags.return_value = ('v1.1.0', ['0.1.0', '1.1.0'])

        got = resolve_deps.check_constraint('ministryofjustice', 'simple-formula', None)
        self.assertEqual('v1.1.0', got, 'No constraint, just give latest release')

        mock_get_tags.assert_called_with('ministryofjustice', 'simple-formula')

    @patch.object(resolve_deps, 'get_tags')
    def test_check_constraint_gt(self, mock_get_tags):
        mock_get_tags.return_value = ('v1.1.0', ['0.1.0', '1.1.0'])

        got = resolve_deps.check_constraint('ministryofjustice', 'simple-formula', '>=v1.0.0')
        self.assertEqual('v1.1.0', got, 'We asked for >=v1.0.0')

        mock_get_tags.assert_called_with('ministryofjustice', 'simple-formula')

    @patch.object(resolve_deps, 'get_tags')
    def test_check_constraint_lt(self, mock_get_tags):
        mock_get_tags.return_value = ('v1.1.0', ['0.1.0', '1.1.0'])

        got = resolve_deps.check_constraint('ministryofjustice', 'simple-formula', '<=v1.0.0')
        self.assertEqual('v0.1.0', got, 'We asked for <=v1.0.0')

        mock_get_tags.assert_called_with('ministryofjustice', 'simple-formula')

    # Non semver tags doesn't seem to be working right now.
    @unittest.expectedFailure
    @patch.object(resolve_deps, 'get_tags')
    def test_check_constraint_prerelease(self, mock_get_tags):
        mock_get_tags.return_value = ('v1.1.0', ['0.1.0', '1.1.0'])

        got = resolve_deps.check_constraint('ministryofjustice', 'simple-formula', '==v1.0.0-dev.lpa')
        self.assertEqual('v0.1.0', got, 'We asked for a specific version')

        mock_get_tags.assert_called_with('ministryofjustice', 'simple-formula')

    @responses.activate
    @patch.object(resolve_deps, 'check_constraint')
    def test_get_reqs_has_metadata(self, mock_check_constraint):
        metadata = {
            'dependencies': [
                'git@github.com:ministryofjustice/firewall-formula.git',
                'git@github.com:ministryofjustice/repos-formula.git',
            ]
        }

        responses.add(
            responses.GET,
            "https://raw.githubusercontent.com/ministryofjustice/simple-formula/v1.1.0/metadata.yml",
            body=yaml.dump(metadata)
        )

        mock_check_constraint.return_value = 'v1.1.0'

        reqs = resolve_deps.get_reqs('ministryofjustice', 'simple-formula')

        self.assertEqual({
            'tag': 'v1.1.0',
            'deps': [
                ['ministryofjustice', 'firewall-formula', ''],
                ['ministryofjustice', 'repos-formula', '']
            ],
            'metadata': metadata
        }, reqs)

    @responses.activate
    @patch.object(resolve_deps, 'check_constraint')
    def test_get_reqs_no_metadata(self, mock_check_constraint):
        formula_requirements = [
            'git@github.com:ministryofjustice/firewall-formula.git',
            'git@github.com:ministryofjustice/repos-formula.git',
        ]

        responses.add(
            responses.GET,
            "https://raw.githubusercontent.com/ministryofjustice/simple-formula/v1.1.0/metadata.yml",
            status=404
        )
        responses.add(
            responses.GET,
            "https://raw.githubusercontent.com/ministryofjustice/simple-formula/v1.1.0/formula-requirements.txt",
            body="\n".join(formula_requirements)
        )

        mock_check_constraint.return_value = 'v1.1.0'
        reqs = resolve_deps.get_reqs('ministryofjustice', 'simple-formula')

        self.assertEqual({
            'tag': 'v1.1.0',
            'deps': [
                ['ministryofjustice', 'firewall-formula', ''],
                ['ministryofjustice', 'repos-formula', '']
            ],
        }, reqs)

        mock_check_constraint.assert_called_once_with('ministryofjustice', 'simple-formula', None)

    @responses.activate
    @patch.object(resolve_deps, 'check_constraint')
    def test_get_reqs_with_version_constraint(self, mock_check_constraint):
        metadata = {
            'dependencies': [
                'git@github.com:ministryofjustice/firewall-formula.git',
            ]
        }

        responses.add(
            responses.GET,
            "https://raw.githubusercontent.com/ministryofjustice/simple-formula/v1.0.0/metadata.yml",
            body=yaml.dump(metadata)
        )

        mock_check_constraint.return_value = 'v1.0.0'

        reqs = resolve_deps.get_reqs('ministryofjustice', 'simple-formula', 'v1.0.0')

        self.assertEqual({
            'tag': 'v1.0.0',
            'deps': [
                ['ministryofjustice', 'firewall-formula', ''],
            ],
            'metadata': metadata,
        }, reqs)

    @patch.object(resolve_deps, 'get_reqs')
    def test_get_reqs_recursive__simple(self, mock_get_reqs):

        all_formulas = {
            'ministryofjustice/simple-formula': {
                'tag': 'v1.0.1',
                'deps': [
                    ['ministryofjustice', 'firewall-formula', ''],
                ],
            },
            'ministryofjustice/firewall-formula': {
                'tag': 'v1.0.0',
                'deps': [],
            },
        }

        def get_reqs_return_value(org, formula, constraint):
            return all_formulas["{}/{}".format(org, formula)]

        mock_get_reqs.side_effect = get_reqs_return_value

        deps = resolve_deps.get_reqs_recursive([['ministryofjustice', 'simple-formula', '']])

        self.assertEqual(all_formulas, deps)

    @patch.object(resolve_deps, 'get_reqs')
    def test_get_reqs_recursive__loop(self, mock_get_reqs):
        all_formulas = {
            'ministryofjustice/toplevel-formula': {
                'tag': 'v1.0.1',
                'deps': [
                    ['ministryofjustice', 'firewall-formula', ''],
                    ['ministryofjustice', 'looptarget-formula', ''],
                ],
            },
            'ministryofjustice/looptarget-formula': {
                'tag': 'v1.5.0',
                'deps': [
                    ['ministryofjustice', 'intermediate-formula', ''],
                ],
            },
            'ministryofjustice/intermediate-formula': {
                'tag': 'v1.2.0',
                'deps': [
                    ['ministryofjustice', 'looptarget-formula', ''],
                ],
            },
            'ministryofjustice/firewall-formula': {
                'tag': 'v1.0.0',
                'deps': [],
            },
        }

        def get_reqs_return_value(org, formula, constraint):
            return all_formulas["{}/{}".format(org, formula)]

        mock_get_reqs.side_effect = get_reqs_return_value

        deps = resolve_deps.get_reqs_recursive([['ministryofjustice', 'toplevel-formula', '']])

        self.assertEqual(all_formulas, deps)

    @patch.object(resolve_deps, 'get_reqs')
    def test_get_reqs_empty_deps(self, mock_get_reqs):
        all_formulas = {
            'ministryofjustice/simple-formula': {
                'tag' : None,
                'deps': [],
                'metadata': {
                    'entry': None, 
                    'dependencies': None
                 }
            }
        }

        def get_reqs_return_value(org, formula, constraint):
            return all_formulas["{}/{}".format(org, formula)]

        mock_get_reqs.side_effect = get_reqs_return_value

        deps = resolve_deps.get_reqs('ministryofjustice', 'simple-formula', '')

        self.assertEqual({
            'tag' : None,
            'deps': [],
            'metadata': {
                'entry': None, 
                'dependencies': None
             }
        }, deps)

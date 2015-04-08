import os
import re
import sys
import requests
import json
import yaml
import helpers

const_re = re.compile('([=><]+)\s*(.*)')
tag_re = re.compile('v[0-9]+\.[0-9]+\.[0-9]+')


def eq(tag_versions, tag):
    if tag in tag_versions:
        return tag


def ge(tag_versions, tag):
    tag_int = map(int, tag.split('.'))
    if map(int, tag_versions[-1].split('.')) >= tag_int:
        return tag_versions[-1]


def le(tag_versions, tag):
    tag_int = map(int, tag.split('.'))
    for candidate_tag in tag_versions:
        if map(int, candidate_tag.split('.')) <= tag_int:
            return candidate_tag


def lt(tag_versions, tag):
    tag_int = map(int, tag.split('.'))
    for candidate_tag in tag_versions:
        if map(int, candidate_tag.split('.')) < tag_int:
            return candidate_tag


def gt(tag_versions, tag):
    tag_int = map(int, tag.split('.'))
    for candidate_tag in tag_versions:
        if map(int, candidate_tag.split('.')) > tag_int:
            return candidate_tag

constraint_map = {'==': eq,
                  '>=': ge,
                  '<=': le,
                  '<': lt,
                  '>': gt}


def get_tags(org_name, formula_name):
    def convert_tagname(tag):
        try:
            return map(int, tag.split('.'))
        except ValueError:
            print 'Invalid tag {0}'.format(tag)
            return []


    github_token = helpers.get_valid_github_token()
    if not github_token:
        sys.exit(1)

    tags_url = 'https://api.github.com/repos/{0}/{1}/tags'
    tag_versions = []
    tags_json = requests.get(tags_url.format(org_name, formula_name),
                             auth=(github_token, 'x-oauth-basic'))
    # Check for successful access and any credential problems
    if helpers.validate_github_access(tags_json):
        tag_data = json.loads(tags_json.text)
        tag_versions = [x['name'][1:] for x in tag_data]
        tag_versions.sort(key=convert_tagname)
        wanted_tag = 'v{0}'.format(tag_versions[-1])
    else:
        wanted_tag = 'master'
    return wanted_tag, tag_versions


def validate_non_tag(op, text):
    if op != '==':
        raise Exception('SHA/branches can only have == operator')
    return text


def check_constraint(org_name, formula_name, constraint):

    wanted_tag, tag_versions = get_tags(org_name, formula_name)

    if not constraint:
        return wanted_tag

    const_match = re.match(const_re, constraint)
    if not const_match:
        raise Exception('Invalid constraint ({}) for formula {}/{}'.format(
            constraint, org_name, formula_name))

    op, tag = const_match.groups()
    if not re.match(tag_re, tag):
        wanted_tag = validate_non_tag(op, tag)
    elif op not in constraint_map:
        raise Exception('Invalid operator: {}'.format(op))
    elif tag_versions:
        res = constraint_map[op](tag_versions, tag[1:])
        wanted_tag = 'v{}'.format(res) if res else None
    elif wanted_tag == 'master' and not tag_versions:
        raise Exception('Constraint {} cannot be satisfied for {}/{}'.format(
                constraint, org_name, formula_name))
    return wanted_tag


def get_reqs(org_name, formula_name, constraint=None):
    github_token = helpers.get_valid_github_token()
    if not github_token:
        sys.exit(1)

    print 'Processing {0}/{1}'.format(org_name, formula_name)
    req_url = 'https://raw.githubusercontent.com/{0}/{1}/{2}/{3}'
    reqs_file = 'formula-requirements.txt'
    metadata_file = 'metadata.yml'

    wanted_tag = check_constraint(org_name, formula_name, constraint)

    # Get metadata from formula repo. If not found fall back to
    # formula-requirements.txt
    data = {}
    metadata = requests.get(req_url.format(org_name, formula_name,
                                           wanted_tag, metadata_file),
                            auth=(github_token, 'x-oauth-basic'))

    found_metadata = False
     # Check for successful access and any credential problems
    if helpers.validate_github_access(metadata):
        found_metadata = True
        # Read in the yaml metadata from body, stripping out duplicate entries
        data = helpers.parse_metadata(yaml.load(metadata.text))
        reqs = data['dependencies'] if 'dependencies' in data and data['dependencies'] else []
    else:
        reqs = requests.get(req_url.format(org_name, formula_name,
                                           wanted_tag, reqs_file),
                            auth=(github_token, 'x-oauth-basic'))
        if reqs.status_code != 200:
            return {'tag': wanted_tag, 'deps': []}
        reqs = filter(lambda x: len(x) > 0, reqs.text.split('\n'))

    out = []
    if reqs:
        for req in reqs:
            org, formula = req.split(':')[1].split('.git')[0].split('/')
            constraint = req.split('.git')[1] if found_metadata else ''
            out.append(map(str, (org, formula, constraint)))

    res = {'tag': wanted_tag, 'deps': out}
    if data:
        res['metadata'] = data
    return res


def get_reqs_recursive(formulas, deps=None, pins=None,
                       top_level=True, root_formulas=None):
    if deps is None:
        deps = {}
        root_formulas = formulas
    for org_name, formula_name, constraint in formulas:
        key = '%s/%s' % (org_name, formula_name)
        if not top_level and any([x[0] == org_name and x[1] ==
                              formula_name in x for x in root_formulas]):
            # formula in root_formulas so skipping for now
            # if we don't then any tag may get overwriten.
            continue
        if key not in deps:
            # if in deps then it's been processed already
            pin = pins[key] if (pins and key in set(pins)) else None
            constraint = pin if pin else constraint

            deps[key] = get_reqs(org_name, formula_name, constraint=constraint)
            formulas = deps[key]['deps']
            ret = get_reqs_recursive(formulas, deps=deps, pins=pins,
                                     top_level=False, root_formulas=root_formulas)
            deps.update(ret)
    return deps

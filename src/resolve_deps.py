import os
import requests
import json
import yaml

github_token = os.environ.get('GITHUB_TOKEN', None)


def get_reqs(org_name, formula_name):
    if not github_token:
        print 'GITHUB_TOKEN is not defined. Aborting'
        sys.exit(1)

    print 'Getting {0}/{1}'.format(org_name, formula_name)
    tags_url = 'https://api.github.com/repos/{0}/{1}/tags'
    req_url = 'https://raw.githubusercontent.com/{0}/{1}/{2}/{3}'
    reqs_file = 'formula-requirements.txt'
    metadata_file = 'metadata.yml'
    tags_json = requests.get(tags_url.format(org_name, formula_name),
                             auth=(github_token, 'x-oauth-basic'))

    if tags_json.status_code == 200:
        tag_data = json.loads(tags_json.text)
        tag_versions = [x['name'][1:] for x in tag_data]
        tag_versions.sort(key=lambda s: map(int, s.split('.')))
        latest_tag = 'v{0}'.format(tag_versions[-1])
    else:
        latest_tag = 'master'

    # Get metadata from formula repo. If not found fall back to
    # formula-requirements.txt
    data = {}
    metadata = requests.get(req_url.format(org_name, formula_name,
                                           latest_tag, metadata_file),
                            auth=(github_token, 'x-oauth-basic'))

    if metadata.status_code == 200:
        data = yaml.load(metadata.text)
        reqs = data['dependencies']
    else:
        reqs = requests.get(req_url.format(org_name, formula_name,
                                           latest_tag, reqs_file),
                            auth=(github_token, 'x-oauth-basic'))
        if reqs.status_code != 200:
            return {'tag': latest_tag, 'deps': []}
        reqs = filter(lambda x:len(x) > 0, reqs.text.split('\n'))
    out = []
    for req in reqs:
        org, formula = req.split(':')[1].split('.git')[0].split('/')
        out.append(map(str, (org, formula)))

    res = {'tag': latest_tag, 'deps': out}
    if data:
        res['metadata'] = data
    return res


def get_reqs_recursive(org_name, formula_name, deps={}):
    key = '%s/%s' % (org_name, formula_name)
    deps[key] = get_reqs(org_name, formula_name)

    for org, formula in deps[key]['deps']:
        if '%s/%s' % (org, formula) not in deps:
            ret = get_reqs_recursive(org, formula, deps)
            deps.update(ret)
    return deps

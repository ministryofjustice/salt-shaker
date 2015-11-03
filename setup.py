from setuptools import setup

setup(
    name='salt-shaker',
    version='1.0.1',
    packages=['shaker',
              'shaker.libs'],
    url='http://github.com/ministryofjustice/salt_shaker',
    license='',
    author='MoJ DS Infrastucture Team',
    author_email='webops@digital.justice.gov.uk',
    description='',
    install_requires=[
        'requests[security]',
        'PyYAML',
        'pygit2 >= 0.21.4',
        'parse'
    ],
    tests_require=[
        'responses',
        'testfixtures',
        'mock',
    ],
    test_suite='nose.collector',
    setup_requires=['nose>=1.0'],
    scripts=['scripts/salt-shaker'],
)

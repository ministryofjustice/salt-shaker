from setuptools import setup

setup(
    name='salt-shaker',
    version='0.0.1',
    packages=['shaker'],
    url='http://github.com/ministryofjustice/salt_shaker',
    license='',
    author='MoJ DS Infrastucture Team',
    author_email='webops@digital.justice.gov.uk',
    description='',
    install_requires=[
        'requests',
        'PyYAML',
        'pygit2 >= 0.21.4',
    ],
    tests_require=[
        'responses',
    ],
    setup_requires=['nose>=1.0'],
    scripts=['scripts/salt-shaker'],
)

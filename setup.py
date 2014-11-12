from distutils.core import setup

setup(
    name='salt-shaker',
    version='0.0.1',
    package_dir={'': 'src'},
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
    scripts=['scripts/salt-shaker'],
)

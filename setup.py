from distutils.core import setup

setup(
    name='shaker',
    version='0.0.1',
    package_dir={'': 'src'},
    packages=['shaker'],
    url='',
    license='',
    author='MoJ DS Infrastucture Team',
    author_email='webops@digital.justice.gov.uk',
    description='',
    install_requires=[
        'requests',
        'PyYAML',
        'pygit2'
    ],
    dependency_links=[]
)

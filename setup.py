from distutils.core import setup

setup(
    name='shaker',
    version='0.0.1',
    package_dir={'': 'src'},
    py_modules=['shaker', 'salt_shaker', 'resolve_deps'],
    url='',
    license='',
    author='MoJ DS Infrastucture Team',
    author_email='team@digital.justice.gov.uk',
    description='',
    install_requires=[
        'Fabric',
        'GitPython==0.3.2.RC1',
        'requests',
        'PyYAML'
    ]
)

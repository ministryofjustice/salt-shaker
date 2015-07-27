# salt-shaker

## Installation

Opinionated saltstack formula dependency resolver

Note: Install libgit2 with libssh2 support before installing this package.

    $ brew install libgit2 --with-libssh2


## Quickstart

Salt shakers requires an initial config file containing the metadata for the local formula. eg,

```
formula: my_organisation/local-formula

dependencies:
- some_organisation/test1-formula
- another_organisation/testa-formula>=v1.0.0
- another_organisation/testb-formula<=v4.0.0
- another_organisation/testc-formula==v2.0.0
```

To generate and download a list of formula requirements, simply run

    salt-shaker install

This will also save a list of the requirements and their versions, by default in 'formula-requirements.txt'

If this file exists, you can run

    salt-shaker install-pinned-versions

to install the requirements with their versions pinned by the formula requirements file version.

You can also run a check to see what changes would be made to the formula-requirements file if an
install were run.

    salt-shaker check

This is useful to see if the dependency resolution chain has changed since versions
were pinned.

## Introduction

Salt shakers requires an initial config file containing the metadata for the local formula. eg,

```
formula: my_organisation/local-formula

exports:
- local

dependencies:
- some_organisation/test1-formula
- another_organisation/testa-formula>=v1.0.0
- another_organisation/testb-formula<=v4.0.0
- another_organisation/testc-formula==v2.0.0
```

Here, the name of the formula is set to be 'local-formula', with an organisation name of 'my_organisation'.
This formula will have dependencies on the described formula, based on the format 

    <organisation>/<formula-name>(constraint)


### exports
By default formula `organisation/name-formula` will be exposed to salt minions as `name`. So you can later refer to it 
in your sls files using:
```
include:
- name
```

In some cases you might want to overwrite the default export name or even expose multiple exports. In such case add to 
metadata.yml:
```
exports:
- name1
- name2
```

Make sure you have both subdirectories available in formula:
```
\
+ name1/
| + init.sls
|
+ name2/
| + init.sls
|
+ metadata.yml
```

And from now on your formula will supply both exports and you can refer to them with:
```
include:
- name1
- name2
```


### Constraint Resolution
The constraint is optional and can take the form ==, >= or <= followed by a version tag. Salt shaker will use these constraints and the constraints
of any sub-dependencies found recursively on these dependencies, handling conflicts to try and resolve them all to a logically satisfiable single
constraint.

* '==' Equality takes priority over all other constraints, current equalities override any new ones
* '>=' The highest greater than bound takes precedence over the lower
* '<=' least less-than bound takes precedence over the higher
* '>=, <=' Opposite contraints will throw an exception, although these may be resolvable in practice


Constraints specified in the metadata file are parsed first, then these are sequential processed, with the full dependency tree
for that entry being parsed before moving on to the next metadata dependency entry.

### Process
Salt shaker consists of two main processes. Firstly, a metadata resolver that can parse config files and generate a set of formulas with resolved dependencies

This dependency list can then be parsed and resolved into actual tags and sha's on github, downloaded into a local directory, and the set of formula
requirements and their versions stored in a local file. This local file can be used as the base of future updates, so that the remote formulas
versions are in effect 'pinned'.

### Misc Options
There are a few flags that can be passed to alter salt-shakers behaviour.

--enable-remote-check: This will force salt-shaker to contact the remote repository when using pinned versions, updating any
  shas that tags resolve to, meaning that if a tag was moved then the change would be picked up. With the default behaviour
  tags are assumed to be immutable

--simulate: No operation mode where the full command specified will be run, but no alterations will be made to any config files.

--root_dir: Specify the root directory for salt-shaker to work in

--verbose, --debug: Increase the level of logging output from salt-shaker

# Running the tests

It's as simple as running this command:

```
python setup.py nosetests
```

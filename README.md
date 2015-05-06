# salt-shaker

## Installation

Opinionated saltstack formula dependency resolver

Note: Install libgit2 with libssh2 support before installing this package.

    $ brew install libgit2 --with-libssh2


## Quickstart
    
Salt shakers requires an initial config file containing the metadata for the local formula. eg,

	formula: my_organisation/local-formula

	dependencies:
		- some_organisation/test1-formula
		- another_organisation/testa-formula>=v1.0.0
		- another_organisation/testb-formula<=v4.0.0
		- another_organisation/testc-formula==v2.0.0
		
To generate and download a list of formula requirements, simply run

	salt-shaker update
	
This will also save a list of the requirements and their versions, by default in 'formula-requirements.txt'

If this file exists, you can run 

	salt-shaker refresh

to refresh the downloaded requirements, the versions will be pinned by the formula requirements file version but any updates to those tagged 
versions will be downloaded
		
## Introduction

Salt shakers requires an initial config file containing the metadata for the local formula. eg,

	formula: my_organisation/local-formula

	dependencies:
		- some_organisation/test1-formula
		- another_organisation/testa-formula>=v1.0.0
		- another_organisation/testb-formula<=v4.0.0
		- another_organisation/testc-formula==v2.0.0

Here, the name of the formula is set to be 'local-formula', with an organisation name of 'my_organisation'.
This formula will have dependencies on the described formula, based on the format 

	<organisation>/<formula-name>(constraint)

The constraint is optional and can take the form ==, >= or <= followed by a version tag. Salt shaker will use these constraints and the constraints
of any sub-dependencies found recursively on these dependencies, handling conflicts to try and resolve them all to a logically satisfiable single
constraint.

* '==' Equality takes priority over all other constraints, current equalities override any new ones
* '>=' The highest greater than bound takes precedence over the lower
* '<=' least less-than bound takes precedence over the higher
* '>=, <=' Opposite contraints will throw an exception, although these may be resolvable in practice
             
Salt shaker consists of two main sections. Firstly, a metadata resolver that can parse config files and generate a set of formulas with resolved dependencies

This dependency list can then be parsed and resolved into actual tags and sha's on github, downloaded into a local directory, and the set of formula
requirements and their versions stored in a local file. This local file can be used as the base of future updates, so that the remote formulas
versions are in effect 'pinned'. 


## Testing
Hacking on salt-shaker

The test suite can be run via setup.py as follows

    python setup.py nosetests
 


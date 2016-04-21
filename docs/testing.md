# Testing

To run the tests, do:

    ./tests.sh

This looks in the `src/tests/` directory and runs anything it can find using
the [nose](https://nose.readthedocs.org/en/latest/) test runner.

To test a specific module in `src/tests/`, use:

    ./tests.sh modulename

for example:

    ./tests.sh test_buildercore_core
    
will run all of the tests it can find in the `src/tests/test_buildercore_core.py`
module.

To test a specific class (suite) of tests in a module, use:

    ./tests.sh module:class
    
for example:

    ./tests.sh test_builder_core:TestCore
    
## Configuration

The test runner (nose) is configured using the file `.noserc` file in the 
project's root rather than passing many parameters to the runner.

Nose is called in the file `.unittest`.
    
## Coverage

After successfully running the tests a code coverage report is displayed. If the
tests did not successfully complete, this report can still be displayed with the
command:

    coverage report
    
This report is generated from the results stored in `.coverage`
    
## Slow! So slow!

The `tests.sh` script is designed to be run by CI and does a collection of 
convenient things, like creating/activating/populating a virtualenv and project
linting before running the tests. It's not nearly as fast as simply calling the
test runner directly. 

The test runner can be called directly with:

    ./.unittest.sh

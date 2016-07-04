# Testing

Test using:

    ./test.sh

This looks in the `src/tests/` directory and runs anything it can find.

To test a specific module within `src/tests/`, use:

    ./test.sh modulename

for example:

    ./test.sh test_buildercore_core

That will run all tests it can find inside `src/tests/test_buildercore_core.py`.

## Code coverage

A code coverage report is displayed after all tests successfully pass. 

The report can still be displayed if any tests failed with:

    coverage report

This report is generated from the results stored in the `.coverage` file

## Slow! So slow!

The `tests.sh` script is designed to be run by a CI and does several things,
like creating/activating/populating a virtualenv and project linting before
running the unittests. This is unbearably slow.

The test runner can be called directly with:

    ./.unittest.sh

and:

	./.unitest.sh modulename

and:

	./.unittest.sh modulename.SuiteName.method_name
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

The `test.sh` script is designed to be run by a CI and does several things,
like creating/activating/populating a virtualenv and project linting before
running the unittests. This is unbearably slow, after the first run
you can load the virtualenv with:

    source venv/bin/activate

Then, the test runner can be called directly with:

    PYTHONPATH=src green tests

or:

    PYTHONPATH=src green tests.test_buildercore_trop

or:

    PYTHONPATH=src green tests.test_buildercore_trop.TestBuildercoreTrop.test_method_name

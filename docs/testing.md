# Testing

Test using:

    ./test.sh

This looks in the `src/tests/` directory and runs anything it can find.

To test a specific file, use:

    ./test.sh path/to/test/file.py

For example:

    ./test.sh ./src/tests/test_utils.py

That will run all tests it can find inside `src/tests/test_utils.py`.

To test a specific *test* within a specific file, use:

    ./test.sh path/to/test/file.py::function_name
    
For example:

    ./test.sh ./src/tests/test_utils.py::test_coerce_string_value

## Testing during development

Once builder has been installed with:

    ./update.sh
    
and the virtual environment activated with:

    source .activate-venv.sh

the tests can be run directly with:

    ./.test.sh

## Integration tests

'Integration' tests create actual AWS infrastructure and test against that.

They take longer, require more permissions and are typically only run during CI.

To run the integration tests:

    BUILDER_INTEGRATION_TESTS=1 ./test.sh

## Code coverage

A code coverage report is displayed after all tests successfully pass. 

The report can still be displayed if any tests failed with:

    coverage report

This report is generated from the results stored in the `.coverage` file

## Filter single integration tests

Some integration tests run through all the defined projects for regression testing. To filter only a single project, for example to reproduce a failure, you can run:

```
pytest src/integration_tests/test_validation.py::TestValidationElife --filter-project-name=generic-cdn
```

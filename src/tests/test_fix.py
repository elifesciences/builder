import json
import fix
import mock

def test_success():
    assert fix.success()
    assert fix.success("success!")

def test_problem():
    assert fix.problem("foo", "bar") == ("foo", "bar", None)
    assert fix.problem("foo", "bar", "baz") == ("foo", "bar", "baz")

def test_has_nodes():
    cases = [
        ({}, False),
        ({'ec2': False}, False),
        ({'ec2': True}, True), # I don't think this is used/encouraged
    ]
    for given, expected in cases:
        assert fix._has_nodes(given) == expected, "failed on: %s" % given

def test_disclaimer():
    assert fix._disclaimer()

def test_stack_diff():
    pass

def test_aws_drift():
    result = {'foo': 'bar'}
    expected = ('AWS thinks this stack has drifted.', './bldr update_infrastructure:foo--stack', json.dumps(result, indent=4))
    with mock.patch('fix.core.drift_check', return_value=result):
        assert fix._aws_drift('foo--stack') == expected

def test_dns_check():
    pass

def test_format_problem():
    problem = ("Foo :(", "Bar!", "... baz.")
    expected = """problem:  Foo :(
   solution: Bar!
   details:  ... baz."""
    assert fix.format_problem(problem) == expected

def test_print_problem_list():
    problem_list = [
        ("Foo", "Bar", None),
        ("Bar", "Baz", "Bup")
    ]
    assert not fix.print_problem_list(problem_list)

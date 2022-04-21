import pytest
from collections import OrderedDict
from . import base
from functools import partial
from buildercore import utils
from unittest.mock import patch, MagicMock
import logging

LOG = logging.getLogger(__name__)

class Simple(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_ordered_dump(self):
        case_list = [
            ("1", "'1'\n"),
            ({}, "{}\n"),
            # simple bytestrings are treated as regular strings
            (b"1", "'1'\n"),
        ]
        self.assertAllPairsEqual(utils.ordered_dump, case_list)

    def test_shallow_flatten(self):
        case_list = [
            ([], []),
            ([[1], [2], [3]], [1, 2, 3]),
            ([[[1]], [2], [3]], [[1], 2, 3]),
            ([[None]], [None]),
        ]
        for given, expected in case_list:
            self.assertEqual(utils.shallow_flatten(given), expected)

    def test_isint(self):
        expected_true = [
            1, 0, -1,
            "1", "0", "-1"
        ]
        self.assertAllTrue(utils.isint, expected_true)

    def test_isstr(self):
        expected_true = ['', r'']
        self.assertAllTrue(utils.isstr, expected_true)

        # when is a string not a string? when it's a bytestring
        expected_false = b''
        self.assertFalse(utils.isstr(expected_false))

    def test_nth(self):
        expected_vals = [
            ('a', 0, 'a'),
            ('ab', 0, 'a'),
            ('ab', 1, 'b'),
            ('abc', 2, 'c'),
            ([1, 2, 3], 0, 1),
            ([1, 2, 3], 1, 2),
        ]
        for data, n, expected in expected_vals:
            self.assertEqual(expected, utils.nth(data, n))

    def test_wonky_nths(self):
        vals = [
            ('a', 1),
            ([], 1),
            # ({}, 'a'), # now raises a TypeError
        ]
        expected = None
        for data, n in vals:
            self.assertEqual(expected, utils.nth(data, n))

    def test_bad_nths(self):
        vals = [
            ({}, 'a', TypeError),
        ]
        for data, n, exc in vals:
            self.assertRaises(exc, utils.nth, data, n)

    def test_lu(self):
        data = {
            'a': {
                'b': {
                    'c': [1, 2, 3]}}}
        expected = [
            ('a', {'b': {'c': [1, 2, 3]}}),
            ('a.b', {'c': [1, 2, 3]}),
            ('a.b.c', [1, 2, 3])
        ]
        self.assertAllPairsEqual(partial(utils.lu, data), expected)

    def test_lu_with_default(self):
        data = {'a': {'b': {'c': [1, 2, 3]}}}
        expected_default = 'wtf?'
        expected = [
            ('a.b.z', expected_default),
            ('a.y.z', expected_default),
            ('x.y.z', expected_default)
        ]
        self.assertAllPairsEqual(partial(utils.lu, data, default=expected_default), expected)

    def test_lu_no_default(self):
        data = {'a': {'b': {'c': [1, 2, 3]}}}
        self.assertRaises(ValueError, utils.lu, data, 'x.y.z')

    def test_lu_no_context(self):
        data = None
        self.assertRaises(ValueError, utils.lu, data, 'a.b.c')

    def test_lu_no_dict_context(self):
        data = [1, 2, 3]
        self.assertRaises(ValueError, utils.lu, data, 'a.b.c')

    def test_lu_invalid_path(self):
        data = {'a': {'b': {'c': [1, 2, 3]}}}
        self.assertRaises(ValueError, utils.lu, data, None)

    @patch('time.sleep')
    def test_call_while_happy_path(self, sleep):
        check = MagicMock()
        check.side_effect = [True, True, False]
        utils.call_while(check, interval=5)
        self.assertEqual(2, len(sleep.mock_calls))

    @patch('time.sleep')
    def test_call_while_timeout(self, sleep):
        check = MagicMock()
        check.return_value = True
        try:
            utils.call_while(check, interval=5, timeout=15)
            self.fail("Should not return normally")
        except BaseException:
            self.assertEqual(3, len(sleep.mock_calls))

    @patch('time.sleep')
    def test_call_while_timeout_inner_exception_message(self, sleep):
        check = MagicMock()
        check.return_value = RuntimeError("The answer is not 42")
        try:
            utils.call_while(check, interval=5, timeout=15)
            self.fail("Should not return normally")
        except BaseException as e:
            self.assertIn("(The answer is not 42)", str(e))

    @patch('time.sleep')
    def test_call_while_custom_exception(self, sleep):
        check = MagicMock()
        check.return_value = True
        try:
            utils.call_while(check, interval=5, timeout=15, exception_class=OSError)
            self.fail("Should not return normally")
        except OSError as e:
            self.assertEqual("Reached timeout 15 while waiting ...", str(e))

    @patch('time.sleep')
    def test_call_while_custom_message(self, sleep):
        check = MagicMock()
        check.return_value = True
        try:
            utils.call_while(check, interval=5, timeout=15, update_msg="waiting for Godot")
            self.fail("Should not return normally")
        except BaseException as e:
            self.assertEqual("Reached timeout 15 while waiting for Godot", str(e))

    def test_ensure(self):
        utils.ensure(True, "True should allow ensure() to continue")
        self.assertRaises(AssertionError, utils.ensure, False, "Error message")

        class CustomException(Exception):
            pass
        self.assertRaises(CustomException, utils.ensure, False, "Error message", CustomException)

    def test_nested_dictmap(self):
        "nested_dictmap transforms a dictionary recursively as expected"
        vals = {'foo': 'pants', 'bar': 'party'}

        def func(v):
            return v.format(**vals) if utils.isstr(v) else v

        cases = [
            # given, expected, fn
            ({'a': 'b'}, {'a': 'b'}, None), # no function, does nothing
            ({'a': 'b'}, {'a': 'b'}, lambda k, v: (k, v)), # returns inputs
            ({'a': 'b'}, {'a': 'b'}, lambda k, v: (LOG.debug(k + v), (k, v))[1]), # side effects

            # keys as well as values are updated
            ({'a': {'b': {'{foo}': '{bar}'}}}, {'a': {'b': {'pants': 'party'}}}, lambda k, v: (func(k), func(v))),
        ]
        for given, expected, fn in cases:
            self.assertEqual(expected, utils.nested_dictmap(fn, given))

    def test_nested_dictmap_2(self):
        "nested_dictmap visits replacements too"
        def fn(k, v):
            if k == 'a':
                return k, {'{foo}': v}
            k = k.format(foo='bar')
            return k, v
        cases = [
            ({'a': 'b'}, {'a': {'bar': 'b'}}, fn),
        ]
        for given, expected, func in cases:
            self.assertEqual(expected, utils.nested_dictmap(func, given))

#

def test_visit():
    "`visit` can pass a value or object through unmodified."
    cases = [
        (None, None),
        (True, True),
        ("", ""),
        ({}, {}),
        ([], []),
        (OrderedDict(), OrderedDict())
    ]

    def identity(value):
        return value

    for given, expected in cases:
        assert utils.visit(given, identity) == expected, "failed case: %r" % given

def test_visit__modify():
    "`visit` can modify top-level as well as deeply-nested values in place."
    cases = [
        (None, None),
        (1, 1),
        (2, 2),
        (3, 'fizz'),
        (4, 4),
        (5, 'buzz'),
        (15, 'fizzbuzz'),
        ({3: 3}, {3: 'fizz'}),
        ({'foo': {'bar': {'baz': ['bup', 1, 2, 3, 4, 5, 15]}}},
         {'foo': {'bar': {'baz': ['bup', 1, 2, 'fizz', 4, 'buzz', 'fizzbuzz']}}})
    ]

    def f(value):
        if not isinstance(value, int):
            return value
        if not value % 3 and not value % 5:
            return 'fizzbuzz'
        if not value % 3:
            return 'fizz'
        if not value % 5:
            return 'buzz'
        return value

    for given, expected in cases:
        assert utils.visit(given, f) == expected, "failed case: %r" % given

def test_updatein__no_create():
    cases = [
        (({}, '', "foo"), {'': "foo"}),
        (({}, None, "foo"), {None: "foo"}),
        (({}, ('foo', 'bar'), 'baz'), {('foo', 'bar'): 'baz'}),
        (({}, 'foo', 'bar'), {'foo': 'bar'}),
        (({'foo': 'bar'}, 'foo', 'baz'), {'foo': 'baz'}),
        (({'foo': {'bar': 'baz'}}, 'foo.bar', 'bup'), {'foo': {'bar': 'bup'}}),
    ]
    for (given, path, newval), expected in cases:
        # all cases should pass regardless of whether create is True or False
        for create in [False, True]:
            assert utils.updatein(given, path, newval, create) == expected

def test_updatein__no_create_error():
    "when create=False, a KeyError is raised if a path segment can't be reached"
    with pytest.raises(KeyError):
        utils.updatein({}, 'foo.bar', 'baz', create=False)

def test_updatein__create():
    "when create=True, deeply nested maps can be made"
    cases = [
        (({}, 'foo.bar', 'baz'), {'foo': {'bar': 'baz'}}),
        (({}, 'foo.bar.baz.bup.boo', 'argh'), {'foo': {'bar': {'baz': {'bup': {'boo': 'argh'}}}}}),
    ]
    for (given, path, newval), expected in cases:
        assert utils.updatein(given, path, newval, create=True) == expected

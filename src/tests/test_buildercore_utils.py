from . import base
from functools import partial
from buildercore import utils
from mock import patch, MagicMock
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
        expected_true = [''] if utils.gtpy2() else ['', r'', u'']
        self.assertAllTrue(utils.isstr, expected_true)

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
            #({}, 'a'), # now raises a TypeError
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
            self.assertIn("(The answer is not 42)", e.message)

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

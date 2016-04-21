from . import base
from functools import partial
from buildercore import utils

class TestBuildercoreUtils(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

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
        data = {'a': {'b': {'c': [1,2,3]}}}
        expected_default = 'wtf?'
        expected = [
            ('a.b.z', expected_default),
            ('a.y.z', expected_default),
            ('x.y.z', expected_default)
        ]
        self.assertAllPairsEqual(partial(utils.lu, data, default=expected_default), expected)

    def test_lu_no_default(self):
        data = {'a': {'b': {'c': [1,2,3]}}}
        self.assertRaises(ValueError, utils.lu, data, 'x.y.z')

    def test_lu_no_context(self):
        data = None
        self.assertRaises(ValueError, utils.lu, data, 'a.b.c')

    def test_lu_no_dict_context(self):
        data = [1,2,3]
        self.assertRaises(ValueError, utils.lu, data, 'a.b.c')

    def test_lu_invalid_path(self):
        data = {'a': {'b': {'c': [1,2,3]}}}
        self.assertRaises(ValueError, utils.lu, data, None)

"""Tests concerning S3 interaction."""

import time
import json
from os.path import join
from . import base
from buildercore import s3
from unittest import skip

class SimpleCases(base.BaseCase):
    def setUp(self):
        s3.delete_contents("test/")
        
    def tearDown(self):
        s3.delete_contents("test/")

    def test_exists(self):
        key = "test/boo"
        self.assertFalse(s3.exists(key))
    
    def test_writable(self):
        key = "test/foo"
        self.assertFalse(s3.exists(key))
        s3.write(key, "asdf")
        self.assertTrue(s3.exists(key))

    def test_overwrite(self):
        key = "test/foo"
        self.assertFalse(s3.exists(key))
        s3.write(key, "asdf")
        self.assertRaises(KeyError, s3.write, key, "fdsa")

    def test_delete(self):
        key = "test/foo"
        s3.write(key, "asdf")
        self.assertTrue(s3.exists(key))
        s3.delete(key)
        self.assertFalse(s3.exists(key))

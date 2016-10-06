"""Tests concerning S3 interaction."""
import os
from . import base
from buildercore import s3

class SimpleCases(base.BaseCase):
    def setUp(self):
        s3.delete_contents("test/")
        os.system("mkdir -p /tmp/builder/")

    def tearDown(self):
        s3.delete_contents("test/")
        os.system("rm -f /tmp/builder/*")

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
        s3.write(key, "fdsa", overwrite=True)

        # TODO: test content was actually overwritten

    def test_delete(self):
        key = "test/foo"
        s3.write(key, "asdf")
        self.assertTrue(s3.exists(key))
        s3.delete(key)
        self.assertFalse(s3.exists(key))

    def test_list(self):
        keys = [
            "test/foo",
            "test/bar",
            "test/baz"
        ]
        for key in keys:
            s3.write(key, 'asdf')
        self.assertEqual(sorted(keys), sorted(s3.simple_listing("test/")))

    def test_download(self):
        key = "test/baz"
        expected_contents = "test content"
        expected_output = '/tmp/builder/baz'
        s3.write(key, expected_contents)
        s3.download(key, expected_output)
        self.assertTrue(os.path.exists(expected_output))
        self.assertEqual(open(expected_output, 'r').read(), expected_contents)

"""Tests concerning S3 interaction."""
import os
from . import base
from buildercore import s3, utils

class TestReadWrite(base.BaseCase):
    def setUp(self):
        self.envname = base.generate_environment_name()

        self.prefix = "test/%s" % self.envname
        s3.delete_contents("%s/" % self.prefix)

        self.local_path, self.local_cleanup = utils.tempdir()
        os.system("mkdir -p %s" % self.local_path)

    def tearDown(self):
        s3.delete_contents("%s/" % self.prefix)
        self.local_cleanup()

    def test_exists(self):
        key = "%s/boo" % self.prefix
        self.assertFalse(s3.exists(key))

    def test_writable(self):
        key = "%s/foo" % self.prefix
        self.assertFalse(s3.exists(key))
        s3.write(key, "asdf")
        self.assertTrue(s3.exists(key))

    def test_overwrite(self):
        key = "%s/foo" % self.prefix
        self.assertFalse(s3.exists(key))
        s3.write(key, "asdf")
        self.assertRaises(KeyError, s3.write, key, "fdsa")
        s3.write(key, "fdsa", overwrite=True)

    def test_delete(self):
        key = "%s/foo" % self.prefix
        s3.write(key, "asdf")
        self.assertTrue(s3.exists(key))
        s3.delete(key)
        self.assertFalse(s3.exists(key))

    def test_list(self):
        keys = [
            "%s/foo-%s" % (self.prefix, base.generate_environment_name()),
            "%s/bar-%s" % (self.prefix, base.generate_environment_name()),
            "%s/baz-%s" % (self.prefix, base.generate_environment_name()),
        ]
        for key in keys:
            s3.write(key, 'asdf')
        list_result = sorted(s3.simple_listing("%s/" % self.prefix))
        for key in keys:
            self.assertIn(key, list_result)

    def test_download(self):
        key = "%s/foo" % self.prefix
        expected_contents = "test content"
        expected_output = '%s/baz' % self.local_path
        s3.write(key, expected_contents)
        s3.download(key, expected_output)
        self.assertTrue(os.path.exists(expected_output))
        self.assertEqual(open(expected_output, 'r').read(), expected_contents)

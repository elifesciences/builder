from os import remove
from . import base
from buildercore import cfngen, context_handler

class TestBuildercoreContext(base.BaseCase):
    def setUp(self):
        print context_handler.delete_context_from_s3('dummy1--prod')

    def test_storing_a_context_on_s3_and_retrieving_it_from_a_new_client(self):
        stackname = 'dummy1--prod'
        context = cfngen.build_context('dummy1', stackname=stackname)
        context_handler.write_context(stackname, context)
        expected = context_handler.load_context(stackname)

        remove(context_handler.local_context_file(stackname))
        downloaded = context_handler.load_context(stackname)

        self.assertEqual(expected, downloaded)

    def _read_file(self, path):
        with open(path) as f:
            return f.read()

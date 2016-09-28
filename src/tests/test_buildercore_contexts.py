import json
from os import remove
from . import base
from buildercore import cfngen, contexts

class TestBuildercoreContext(base.BaseCase):
    def setUp(self):
        contexts.delete_context_from_s3('dummy1--prod')

    def test_storing_and_retrieving_a_context(self):
        stackname = 'dummy1--prod'
        context = cfngen.build_context('dummy1', stackname=stackname)
        cfngen.write_context(stackname, json.dumps(context))
        expected = self._read_file(contexts.local_context_file(stackname))

        contexts.write_context_to_s3(stackname)
        remove(contexts.local_context_file(stackname))
        downloaded = contexts.download_from_s3(stackname)
        
        self.assertEqual(expected, self._read_file(downloaded))

    def _read_file(self, path):
        with open(path) as f:
            return f.read()


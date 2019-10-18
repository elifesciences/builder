import os, sys
from . import base
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import taskrunner as tr
#from buildercore import cfngen, context_handler
#from cfn import ssh, owner_ssh, generate_stack_from_input
from mock import patch
#from contextlib import redirect_stdout # py3 only

def capture_stdout(f):
    strbuffer = StringIO()
    sys.stdout = strbuffer
    try:
        return {"result": f(),
                "stdout": strbuffer.getvalue()}
    except BaseException as e:
        return {"result": e,
                "stdout": strbuffer.getvalue()}
    finally:
        sys.stdout = sys.__stdout__

class TaskRunner(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_list_tasks(self):
        "printing the list of commands can be invoked in many different ways"
        list_tasks_invocations = [
            "", # no args
            "-l", "--list", 
            "", "-h", "--help", "-?"]
        for invocation in list_tasks_invocations:
            result = capture_stdout(lambda: tr.main([invocation]))
            self.assertEqual(result["result"], 0)

    def test_commands_are_present(self):
        "some common commands we always use are in the list and qualified as necessary"
        expected = [
            "ssh", "master.download_keypair",
            "launch", "masterless.launch",
            "start", "stop", "restart",
            "buildvars.switch_revision"
        ]
        result = capture_stdout(lambda: tr.main(["--list"]))
        for case in expected:
            present = False
            for row in result["stdout"].splitlines():
                if row.startswith(case):
                    present = True
                    break
            self.assertTrue(present, "task %r not present in task listing" % case)

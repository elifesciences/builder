import sys
from . import base
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import taskrunner as tr

SUCCESS_RC = 0

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
            response = capture_stdout(lambda: tr.main([invocation]))
            self.assertEqual(response["result"], SUCCESS_RC)

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

    def test_commands_can_be_called(self):
        task_list = tr.generate_task_list()
        result_map = tr.exec_task("ping", task_list)
        expected = {
            'task': 'ping',
            'task_args': [],
            'task_kwargs': {},
            'result': 'pong',
            'rc': SUCCESS_RC}
        self.assertEqual(expected, result_map)

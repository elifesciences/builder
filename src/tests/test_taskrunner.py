import sys
from . import base
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
            ("", 1), # no args
            ("-l", 0),
            ("--list", 0),
        ]
        for invocation, expected_return_code in list_tasks_invocations:
            response = capture_stdout(lambda: tr.main([invocation]))
            self.assertEqual(response["result"], expected_return_code)

    def test_commands_are_present(self):
        "some common commands we always use are in the list and qualified as necessary"
        expected = [
            "ssh", # "master.download_keypair", # requires BLDR_ROLE envvar
            "launch", "masterless.launch",
            "start", "stop", "restart",
            "buildvars.switch_revision"
        ]
        result = capture_stdout(lambda: tr.main(["--list"]))
        for case in expected:
            present = False
            for row in result["stdout"].splitlines():
                if row.strip().startswith(case):
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

    def test_commands_with_args_can_be_called(self):
        task_list = tr.generate_task_list()
        result_map = tr.exec_task("echo:zulu", task_list)
        expected = {
            'rc': 0,
            'result': 'received: zulu',
            'task': 'echo',
            'task_args': ['zulu'],
            'task_kwargs': {}}
        self.assertEqual(expected, result_map)

    def test_commands_with_args_and_kwargs_can_be_called(self):
        task_list = tr.generate_task_list()
        result_map = tr.exec_task("echo:msg,arg,key=val", task_list)
        expected = {
            'rc': 0,
            'result': "received: msg with args: ('arg',) and kwargs: {'key': 'val'}",
            'task': 'echo',
            'task_args': ['msg', 'arg'],
            'task_kwargs': {'key': 'val'}}
        self.assertEqual(expected, result_map)

    def test_commands_with_whitespace_can_be_called(self):
        task_list = tr.generate_task_list()
        # result_map = tr.exec_task("echo:msg,'echo hello world'", task_list) # this is what we give bash
        result_map = tr.exec_task("echo:msg,echo hello world", task_list) # this is what we see after bash
        expected = {
            'task': 'echo',
            'task_args': ['msg', 'echo hello world'],
            'task_kwargs': {},
            'result': "received: msg with args: ('echo hello world',) and kwargs: {}",
            'rc': SUCCESS_RC}
        self.assertEqual(expected, result_map)

    def test_commands_with_special_chars_can_be_called_without_quoting(self):
        task_list = tr.generate_task_list()
        # result_map = tr.exec_task("echo:'hello-world!@$%^&*()-;?/'", task_list) # this is what we give bash
        result_map = tr.exec_task("echo:hello-world!@$%^&*()-;?/", task_list) # this is what we see after bash

        # result_map = tr.exec_task('echo:"hello-world\!@$%^&*()-;?/"', task_list) # double quotes must escape certain shell characters
        # result_map = tr.exec_task('echo:hello-world\\!@$%^&*()-;?/', task_list) # this is what we see after bash with double quotes

        expected = {
            'rc': 0,
            'result': 'received: hello-world!@$%^&*()-;?/',
            'task': 'echo',
            'task_args': ['hello-world!@$%^&*()-;?/'],
            'task_kwargs': {}}
        self.assertEqual(expected, result_map)

    def test_quoted_commands_can_be_called(self):
        task_list = tr.generate_task_list()
        # result_map = tr.exec_task("echo:'hello\, world'", task_list) # this is what we give bash
        result_map = tr.exec_task(r"echo:hello\, world", task_list) # this is what we see after bash
        expected = {
            'rc': 0,
            'result': 'received: hello, world',
            'task': 'echo',
            'task_args': ['hello, world'],
            'task_kwargs': {}}
        self.assertEqual(expected, result_map)

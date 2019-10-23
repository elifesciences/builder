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
        result_map = tr.exec_task("echo:zulu,gamma,a=b,y=z", task_list)
        expected = {
            'rc': 0,
            'result': "received: zulu with args: ('gamma',) and kwargs: {'a': 'b', 'y': 'z'}",
            'task': 'echo',
            'task_args': ['zulu', 'gamma'],
            'task_kwargs': {'a': 'b', 'y': 'z'}}
        self.assertEqual(expected, result_map)

    def test_commands_with_special_chars_can_be_called_without_quoting(self):
        task_list = tr.generate_task_list()
        result_map = tr.exec_task("echo:hello-world!@$%^&*()-;?/", task_list)
        expected = {
            'rc': 0,
            'result': 'received: hello-world!@$%^&*()-;?/',
            'task': 'echo',
            'task_args': ['hello-world!@$%^&*()-;?/'],
            'task_kwargs': {}}
        self.assertEqual(expected, result_map)

    def test_commend_short_circuited_by_comment(self):
        task_list = tr.generate_task_list()
        result_map = tr.exec_task("echo:hell#o-world", task_list)
        expected = {
            'rc': 0,
            'result': 'received: hell',
            'task': 'echo',
            'task_args': ['hell'],
            'task_kwargs': {}}
        self.assertEqual(expected, result_map)

    def test_quoted_commands_can_be_called(self):
        task_list = tr.generate_task_list()
        result_map = tr.exec_task("echo:'hello, world'", task_list)
        expected = {
            'rc': 0,
            'result': 'received: hello, world',
            'task': 'echo',
            'task_args': ['hello, world'],
            'task_kwargs': {}}
        self.assertEqual(expected, result_map)

    def test_multiple_commands_can_be_called(self):
        task_list = tr.generate_task_list()
        result_map_list = tr.exec_many("echo:hello echo:world", task_list)
        expected = [
            {'rc': 0,
             'result': 'received: hello',
             'task': 'echo',
             'task_args': ['hello'],
             'task_kwargs': {}},
            {'rc': 0,
             'result': 'received: world',
             'task': 'echo',
             'task_args': ['world'],
             'task_kwargs': {}}]
        self.assertEqual(expected, result_map_list)

    def test_multiple_commands_can_be_called_with_different_sets_of_params(self):
        task_list = tr.generate_task_list()
        result_map_list = tr.exec_many("echo:hello echo:world,world=round", task_list)
        expected = [
            {'rc': 0,
             'result': 'received: hello',
             'task': 'echo',
             'task_args': ['hello'],
             'task_kwargs': {}},
            {'rc': 0,
             'result': "received: world with args: () and kwargs: {'world': 'round'}",
             'task': 'echo',
             'task_args': ['world'],
             'task_kwargs': {'world': 'round'}}]
        self.assertEqual(expected, result_map_list)

    def test_multiple_quoted_commands_can_be_called(self):
        task_list = tr.generate_task_list()
        result_map_list = tr.exec_many("echo:'hello, world' echo:'fine, thank you',also,response='how are you?'", task_list)
        expected = [
            {'rc': 0,
             'result': 'received: hello, world',
             'task': 'echo',
             'task_args': ['hello, world'],
             'task_kwargs': {}},
            {'rc': 0,
             'result': "received: fine, thank you with args: ('also',) and kwargs: {'response': 'how are you?'}",
             'task': 'echo',
             'task_args': ['fine, thank you', 'also'],
             'task_kwargs': {'response': 'how are you?'}}]
        self.assertEqual(expected, result_map_list)

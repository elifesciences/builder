import subprocess

def execute(cmd):
    return subprocess.check_output(cmd)

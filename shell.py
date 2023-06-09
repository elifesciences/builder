#!/usr/bin/env python
import sys, os
src_dir = os.path.abspath('src')
sys.path.insert(0, src_dir)

try:
    # trigger monkeypatch in threadbare/__init__.py
    # - https://github.com/elifesciences/threadbare/blob/ebf60da4fed5f57e0b231fdaa661b56d1d0a01b9/threadbare/__init__.py#L8
    import threadbare
    from importlib import reload
    from IPython.lib.deepreload import reload as dreload
    from IPython.terminal.embed import InteractiveShellEmbed
    ipshell = InteractiveShellEmbed()
    ipshell()
except ImportError:
    import code
    code.InteractiveConsole(locals=globals()).interact()

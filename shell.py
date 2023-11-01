#!/usr/bin/env python
import os
import sys

src_dir = os.path.abspath('src')
sys.path.insert(0, src_dir)

try:
    # trigger monkeypatch in threadbare/__init__.py
    # - https://github.com/elifesciences/threadbare/blob/ebf60da4fed5f57e0b231fdaa661b56d1d0a01b9/threadbare/__init__.py#L8
    import threadbare  # noqa: F401, I001

    from importlib import reload  # noqa: F401

    from IPython.lib.deepreload import reload as dreload  # noqa: F401
    from IPython.terminal.embed import InteractiveShellEmbed
    print()
    print("'importlib.reload' is available as 'reload'")
    print("'IPython.lib.deepreload.reload' is available as 'dreload'")
    print()
    ipshell = InteractiveShellEmbed()
    ipshell()
except ImportError:
    import code
    print()
    print("ipython not found, using regular shell")
    print()
    code.InteractiveConsole(locals=globals()).interact()

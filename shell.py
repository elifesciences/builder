#!/usr/bin/env python
import sys, os
src_dir = os.path.abspath('src')
sys.path.insert(0, src_dir)

try:
    from buildercore import threadbare # trigger monkeypatch in threadbare/__init__.py
    from importlib import reload
    from IPython.lib.deepreload import reload as dreload
    from IPython.terminal.embed import InteractiveShellEmbed
    ipshell = InteractiveShellEmbed()
    ipshell()
except ImportError:
    import code
    code.InteractiveConsole(locals=globals()).interact()

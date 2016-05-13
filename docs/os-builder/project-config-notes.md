# interfaces for pluggable backends

## project config

* I want to preserve our current method
* I want to plug in a method for controlling access to projects on a per-user basis

current method is:
- project and organisation configuration lives in `projects/org.yaml`
- defaults live at the top of this file in a section called `defaults`
- config snippets live in `projects/org/`
- calling `core.project()` returns a complete set of merged configuration for that project, including org defaults, project overrides and user overrides (snippets).

this approach
- is very convenient
    - for editing
    - understanding how project config works
- doesn't allow hiding or preventing access to projects
    - necessary when dealing with outsiders
    
new method is:
- builder makes a request to a remote builder instance
- that builder authenticates user and returns the project config they are allowed
- remote builder uses current method of project config too, but has access to config not otherwise publicly available.

## salt and pillar data

* I want NO salt or pillar data in the new builder
* I want to specify local paths for development
    - eg, 'salt/' so project 'foo' will look in 'salt/foo/' for 'salt' and 'pillar' directories
* I need all projects to specify a path to their repo config

current method is:
* a single file_mount in `salt/` for 'salt' and 'pillar' directories
* ALL projects using the same `top.sls` files

if the master has no static `top.sls` file, and instead generates one based on the given `minion_id` (https://github.com/saltstack/salt/blob/develop/salt/tops/cobbler.py#L47) we could derive the project name from the minion ID and return something customised just for that project

might be able to generate a top file 

https://docs.saltstack.com/en/latest/topics/master_tops/index.html
https://github.com/saltstack/salt/blob/develop/salt/tops/cobbler.py

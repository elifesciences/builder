# eLife projects

All projects that the builder can build are defined in "project files" that live
in the `./projects/` directory.

Your `settings.yml` file will point to one or many of these project files.

eLife projects are in the `projects/elife.yaml` file and the settings file that
is automatically created when `builder` is installed will point to this. 

A cut-down version of a project file is available in `./projects/example.yaml`
that can be used as a template for creating new project files.

Another cut-down version is `./projects/continuum.yaml`, which is used in our testing infrastructure on an isolated AWS account.

## project file structure

At the top of a project file are the defaults for all projects *in that file*.

All sections beneath the defaults are 'projects'.

If a setting isn't found in a project section, the default from the `defaults` 
section is used.

Some sections are special and don't have the same merging rules. The `aws.rds` 
and `aws.ext` paths will not have default settings merged in if a project doesn't
specify them.

To see the final settings for any project, do:

    $ ./bldr project.data

The above command will prompt you for a project and print other information to 
stdout/stderr. If you want cleanly formatted project data, use the script below:

    $ ./.project.py
    
The above will print a list of projects in YAML.

    $ ./.project.py master-server
    
The above will print the configuration for the `master-server` project in YAML.

    $ ./.project.py master-server format=json
    
The above will print the configuration for the `master-server` project in JSON.

All the scripts starting with `.` require you to first load the Python virtualenv with `source venv/bin/activate`.

## default and alternate configurations

All projects have default Vagrant and AWS configurations, typically in a 
just-works configuration with as few moving parts as possible.

When launching an ad-hoc instance of a project with `./bldr deploy` or `./bldr launch`, the second parameter may specify the `aws-alt` section to use:

    ./bldr deploy:journal,prod
    ./bldr deploy:journal,test

Here an `aws-alt` configuration named `prod` will be used for the `journal` project in the former case, whereas a configuration named `test` will be used in the latter. Everything not specified will be inherited by the `aws` configuration.

Vagrant doesn't support alternate configurations.

## per-user project config overrides

Project configuration can be thought of as a series of maps that are merged 
together (with special rules).

In the `projects` directory you can find the project file `elife.yaml` and a 
directory called `elife`. This `elife` directory contains configuration and 
project state specific to the 'elife' set of projects.

When generating the final project configuration, the project file `elife.yaml` 
is read first, the defaults are extracted and then any further configuration is 
loaded from files in the `elife/` directory ending in `.yaml`.

For example, if a file called 'projects/elife/01-foo.yaml' exists and the 
contents look like:

defaults:
    vagrant:
        cpucap: 50

this will override the default cpucap for *all* projects *unless* a
project in the elife.yaml file specifies a specific cpucap. In which
case, you will then need a snippet for that project too:

elife-website:
    vagrant:
        cpucap: 50

You can have multiple snippets for the same property and the last one
loaded wins. They are loaded in alphabetical order, so zzz-foo.yaml
would win out over aaa-foo.yaml.

## multiple project files

Your `settings.yml` can list multiple project files to inspect. 

The projects in these files are not merged together nor are the defaults shared 
between project files. Projects are file-local.



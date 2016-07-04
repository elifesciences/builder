# eLife projects

All projects that the elife-builder can build are defined in the 
`projects/elife.yaml` file.

At the top of this file are the defaults for all projects. If a setting isn't
found in a project, the default from the `defaults` section is used.

To see the final settings for any project, do:

    $ ./bldr print_project_config

## default and alternate configurations

All projects have default Vagrant and AWS configurations, typically in a 
just-works configuration with as few moving parts as possible.

When launching an ad-hoc instance of a project that has an `aws-alt` section
specified you will be prompted to select an alternate configuration or just skip
selection and go with the default.

When launching an instance using a branch deployment you won't get this prompt.
Instead, if a branch name matches the name of an alternate configuration 
in the project's `aws-alt` section, that configuration will be used. 

For example, an alternate configuration named `master` will be used if launching
an instance of the master (production) branch of a project. This might be a 
larger instance or be backed by an RDS database.

Vagrant doesn't support alternate configurations yet.

## per-user project config overrides

Project configuration can be thought of as a series of maps that are merged 
together (with special rules).

In the `projects` directory you can find the project file `elife.yaml` and a 
directory called `elife`. This `elife` directory contains configuration and 
project state specific to the 'elife' project. 

When creating project config, the project file `elife.yaml` is read first, the
defaults extracted and then any further configuration is loaded from files in 
the `elife/` directory ending in `.yaml`.

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

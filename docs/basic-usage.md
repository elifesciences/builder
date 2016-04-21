## how to use elife-builder

All commands use either the `bldr` script or the `vagrant` command.

### vagrant

Our `Vagrantfile` can build any of our projects, you just need to tell it which 
one.

Typically this is done by selecting the project from the menu:

    $ vagrant up
    You must select a project:

    1 - elife-drupal-dev
    2 - master-server-dev
    3 - ...
    > 

... or it can be done with environment variables:

    $ PROJECT=elife-drupal-dev vagrant up

NOTE: the __dev__ suffix.

Once selected, Vagrant will attempt to provision that machine.

Each project is provisioned in it's own vm with it's own 
started/stopped/provisioned state.

All projects have the `public/` directory as a shared folder mapped to 
`/srv/public` within the guest.

### bldr

There is nothing special about the `bldr` script, it's just a wrapper 
around Fabric's `fab` command, but running within a Python virtualenv.

Fabric's `fab` command looks for a `fabfile.py` in the current directory. 

To list the available commands use `bldr -l`.

Available commands are simply Python functions grouped into modules in the 
`fabfiles/` directory.

To see what stacks AWS knows about, use:

    $ ./bldr aws_stack_list
    
#### stack creation
    
To create a new stack template you can use:

    $ ./bldr create_stack
    
This will read templates from the `stack-templates/` directory 
and prompt you for any parameters the template needs before rendering
the final output to the `stacks/` directory.

The filename of the stack becomes Salt's `minion_id` and the template creation 
should prompt you for this. For example, with `stacks/elife-drupal-foo.yaml` the
`minion_id` is `elife-drupal-foo`.

The `minion_id` is important because it tells Salt what configuration to 
use. See `salt/salt/top.sls` to see which patterns your `minion_id` will match.

The `minion_id` is used interchangably with `instance id`.

At this point you have the opportunity to tweak the CloudFormation stack to
your liking.

To provision and configure your new stack, use:

    $ bldr aws_create_stack

And it will prompt you for the stack to create.

This will then:

1. create the remote stack resources
2. install salt
3. upload the `deploy-user`'s credentials for cloning this project
4. set the `minion-id` and the location of the salt master server.
5. restart `salt-minion`
6. tell the minion to update itself with `salt-call state.highstate`

To both create a new stack and launch it, use:

    $ bldr aws_launch_instance
    
Commands that interact with AWS are prefixed with `aws_`.

To delete a stack you've just created, use:

    $ bldr aws_delete_stack

To update a stack, use:

    $ bldr aws_update_stack

To ssh in to a stack, use:
    
    $ bldr ssh


## Examples

### Creating a new project for development

Scenario: As a developer working on a new project you want to configure a virtual machine for development.

1. Edit the `projects/elife.yaml` file and add your project to the bottom of the file. For example:

        my-project-name:
            vagrant:
                ports: 
                    4321: 80
    This will make Vagrant and the AWS tasks aware of the project and display it in menus.

2. Edit the `salt/salt/top.sls` file and add your project name as a pattern. For example:

        base:
            ...
            'my-project-name-*':
                - myprojectnamedir
            ...
    This will make Salt look in the `salt/salt/myprojectnamedir/` directory for a file called `init.sls` when encountering a minion identifying itself as `my-project-name`.
    
3. Create the directory `salt/salt/myprojectnamedir/` and the file `salt/salt/myprojectnamedir/init.sls`. This file will contain the Salt Stack build instructions for your project across _all_ environments.

4. The `salt/salt/base/` directory contains basic installation instuctions for different types of non-project requirements, like PHP, Python, Ruby, etc. You can reuse them like: 
        base:
            ...
            'my-project-name-*':
                - base.python
                - base.mysql-client
                - myprojectnamedir
            ...

5. Start Vagrant with `vagrant up` and select your project:

        $ vagrant up
        You must select a project:

        1 - my-project-name
        2 - ...
        > 

### Deploying a project instance remotely

Scenario: As a developer working on a project you want to launch a system running the latest version of your project.

1. Create a new stack using Fabric and the `fabfile.py`:

        $ bldr aws_launch_instance
        ...

2. Select an appropriate instance name when it prompts you. __the instance name you pick will determine which entries in the `top.sls` file are matched! and instance name of `test` for the `elife-website` project will match `elife-website-*` and `elife-website-test` in the `top.sls` file but not `elife-website-dev`.

        ...
        > ('elife-website') 12
        instance id [2016-01-11]: 
        > 

Your cloud stack will be created, the build instructions within salt will be followed and an instance of your project will be deployed.

If the project uses a webserver, it will probably be available at `instancename.sub.elifesciences.org`. For example, an instance of the `lax` project called `branch-foo` when deployed will be available at `branch-foo.lax.elifesciences.org`.

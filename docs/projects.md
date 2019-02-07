# eLife projects

eLife projects are in the `projects/elife.yaml` file.

## project file structure

At the top of a project file are the `defaults` for all projects.

All sections beneath the `defaults` are 'projects'.

If a setting isn't found in a project section, the default from the `defaults` 
section is used.

Some sections are special and don't have the same merging rules e.g. the `aws.rds` 
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

All projects have default Vagrant, AWS, and (possibly empty) GCP configurations, typically in a just-works configuration with as few moving parts as possible.

When launching an ad-hoc instance of a project with `./bldr launch`, the third parameter may specify the `aws-alt` and `gcp-alt` sections to use:

    ./bldr launch:journal,my-stack,prod
    ./bldr launch:journal,your-stack,test

Here an `aws-alt` configuration named `prod` will be used for `journal--my-stack` in the former case, whereas a configuration named `test` will be used in the latter. Everything not specified will be inherited by the `aws` configuration.

In case the 3rd argument is omitted, the configuration will default to an `aws-alt` or `gcp-alt` choice that matched the stack instance name:

    ./bldr launch:journal,my-stack,prod

will default to the `prod` configuration.

Vagrant doesn't support alternate configurations.

## elife-builder tech

elife-builder:

* is a [Python](https://www.python.org/) language project
* uses [Fabric](http://www.fabfile.org/) to run commands locally and remotely
* runs within a [Virtualenv](http://docs.python-guide.org/en/latest/dev/virtualenvs/)
* a script [`bldr`](https://github.com/elifesciences/elife-builder/blob/master/bldr) that wraps the Fabric `fab` command in an activated Virtualenv

and ...

* [Vagrant](https://www.vagrantup.com/) for creating, running and managing _local_ [Virtualbox](https://www.virtualbox.org/) machines
* [Amazon AWS services](http://aws.amazon.com/) for creating, running and managing _remote_ machines

as well as ...

* [AWS CloudFormation](http://aws.amazon.com/cloudformation/) templates for describing stacks of AWS services
* [Amazon S3](http://aws.amazon.com/s3/) for storing these CloudFormation templates
* the [Boto library](https://github.com/boto/boto) for communication between Fabric tasks and AWS services

but most importantly:

* [Salt](http://saltstack.com/), to describe what these local and remote machines must be

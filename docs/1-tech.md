# `builder` tech

`builder`:

* is a [Python](https://www.python.org/) language project
* uses [Fabric](http://www.fabfile.org/) to run commands locally and remotely
* runs within a [virtualenv](http://docs.python-guide.org/en/latest/dev/virtualenvs/)
* a bash script [`bldr`](https://github.com/elifesciences/elife-builder/blob/master/bldr) that wraps  Fabric's `fab` command in an activated virtualenv

and ...

* [Vagrant](https://www.vagrantup.com/) for creating, running and managing *local* [Virtualbox](https://www.virtualbox.org/) project instances
* [Amazon AWS services](http://aws.amazon.com/) for creating, running and managing _remote_ project instances

as well as ...

* [AWS CloudFormation](http://aws.amazon.com/cloudformation/) templates for describing stacks of AWS services
* the [Boto library](https://github.com/boto/boto) for communication between Fabric tasks and AWS services

but most importantly:

* [Salt](http://saltstack.com/), to describe what these local and remote environments must be
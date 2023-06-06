# `builder` tech

`builder`:

* is a [Python](https://www.python.org/) language project
* uses [Threadbare](https://github.com/elifesciences/threadbare) to run commands locally and remotely
* has a bash script [`bldr`](https://github.com/elifesciences/elife-builder/blob/master/bldr) that wraps running commands

It has the following responsibilities:

* provisioning: creating cloud resources such as virtual machines, buckets, queues, etc via AWS CloudFormation.
* automation: installing software stacks on virtual machines (Salt)
* orchestration: connecting projects together in their environments (CloudFormation, Boto)
* discovery: allowing developers to list and access projects servers (CloudFormation, SSH)
* deployment: allowing developers and CI systems to change a project version on a deployment

It builds on top of:

* [Vagrant](https://www.vagrantup.com/) for creating, running and managing *local* [Virtualbox](https://www.virtualbox.org/) project instances
* [Amazon AWS services](http://aws.amazon.com/) for creating, running and managing *remote* project instances

as well as ...

* [AWS CloudFormation](http://aws.amazon.com/cloudformation/) templates for describing stacks of AWS services
* the [Boto library](https://github.com/boto/boto) for communication between tasks and AWS services

but most importantly:

* [Salt](http://saltstack.com/), to describe what these local and remote environments must be, in a consistent way no matter if you are inside a VM or a EC2 instance.

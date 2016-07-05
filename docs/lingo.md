# lingo

A Cloudformation TEMPLATE describes a STACK of AWS resources using JSON.

Builder describes PROJECTS and their environment requirements in the project file using YAML.

A STACKNAME is the unique name of a PROJECT INSTANCE of a Cloudformation resource STACK.

It comprises the PROJECT NAME, an INSTANCE-ID and an optional CLUSTER-ID, all delimited by double hyphens.

For example, "elife-lax--master" is the project "elife-lax" with the identifier "master" in the default (unnamed) cluster.

"elife-lax--master--testing" is like the above, but in the 'testing' cluster.



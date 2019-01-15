# Lingo

Builder describes `projects` and their environment requirements in the project file using YAML.

A `stackname` is the unique name of a `project` instance, pointing to a single `stack` (of resources).

It comprises the `project name` and an `instance id`, usually indicating an `environment`, delimited by double hyphens.

For example, `journal--prod` is the project `journal` within the environment `prod`. `journal--20170601` is the project `journal` where the instance id is used to indicate an ad-hoc instance used for tests rather than a environment.

## Generation process

From YAML abstract definitions an intermediate `context` is generated (`.cfn/contexts`) in JSON format. This is stored remotely in an S3 bucket dedicated to builder, and also deployed to EC2 instances so that they can use it to configure themselves e.g. pulling a database password from it.

From the context, multiple provisioning system can be used for each stack:

- a Cloudformation `template` that describes a `stack` of AWS resources using JSON is generated (`.cfn/stacks`). This template does not just describe the EC2 instances but also additional resources such as RDS databases, DNS entries, S3 buckets, SQS queues, Elastic Load Balancers, and everything AWS-related.
- a Terraform folder of disparate resources is generated (`.cfn/terraform/`) for services that are not tied to AWS like Google Cloud Platform or Fastly.

## Multiple nodes

A stack may have from 0 to N identical servers called `nodes`. The set of all nodes for that stack is called a `cluster`. Each node has a progressive number giving it an identity, starting from `1`.

A primary node is defined as node 1 of a cluster. Sometimes this node is special as it runs processes like a testing database or a unique process that should not be running on other nodes.

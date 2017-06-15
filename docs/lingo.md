# lingo

Builder describes `projects` and their environment requirements in the project file using YAML.

From this abstract definitions an intermediate `context` is generated (`.cfn/contexts`) in JSON format. This is deployed to EC2 instances so that they can use it to configure themselves e.g. pulling a database password from it.

From the context, a Cloudformation `template` that describes a `stack` of AWS resources using JSON is generated (`.cfn/stacks`). This template does not just describe the EC2 instances but also additional resources such as RDS databases, DNS entries, S3 buckets, SQS queues, Elastic Load Balancers, and so on.

A `stackname` is the unique name of a `project` instance, pointing to a single Cloudformation resource `stack`.

It comprises the `project name` and an `instance id`, usually indicating an `environment`, delimited by double hyphens.

For example, `journal--prod` is the project `journal` within the environment `prod`. `journal--20170601` is the project `journal` where the instance id is used to indicate an ad-hoc instance used for tests rather than a environment.


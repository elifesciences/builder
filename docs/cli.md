# Main CLI usage

## `launch`

Creates a new [stack](lingo.md). 

Arguments:

- `pname`: name of the project e.g. `journal`
- `instance_id`: name of this instance of the project e.g. `staging`, `prod`, `my-test`
- `alt_config` (optional): name of an alternate configuration to use e.g. `standaone`, `fresh`, `1804`

## `destroy`

Completely deletes an existing stack. Requires confirmation.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`

## `update`

Updates the stateful resources in a stack, mainly re-running Salt on servers to apply a formula or configuration change.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`

## `update_infrastructure`

Updates the infrastructure in a stack, e.g. Fastly CDNs, S3 or GCS buckets, DNS, RDS, ...

Requires extensive permissions to run.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`

## `cmd`

Executes a command on all the servers in a stack.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`
- `command`: command to execute e.g. `ls-l`

## `ssh`

Opens a shell on one of the servers in a stack.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`
- `node`: number identifying the node e.g. `1`

## `switch_revision_update_instance`

Update the stateful `revision` in a stack to change the version of the main application deployed in it, and executes `update` to apply this change.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`
- `revision`: a revision name or SHA, e.g. a Git tag or branch, or a Docker image tag

## `start`

Boots servers in a stack. Idempotent.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`

## `stop`

Shutdowns servers in a stack. Idempotent.

Arguments:

- `stackname`: name of the stack e.g. `journal--end2end`

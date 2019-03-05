# Upgrade the OS version of an instance, with some downtime

## Assumptions

- At least 1 EC2 node is used in a single stack.
- The stack being modifies is called `my-project--my-environment`.
- The change is going from `14.04` to `16.04`.
- This process has only been tested on `elife-libraries` that has already `domain: False`.

## Procedure

### Remove additional DNS

Add:

- `domain: False`
- `intdomain: False`

to the project configuration, if not already present. Change them to `False` if they already have a different value.

After running `bldr update_infrastructure:my-project--my-environment,skip=ec2`, check that Route 53 does not have DNS entries left relating directly to EC2 instances.

### Destroy node

Add `ec2.suppressed` with the value `[1]`, and run `update_infrastructure,skip=ec2`.

Optional `ext` volumes will not be removed, but their mount point onto the corresponding instance will be deleted.

To fully clear the existence of node 1, run also:
```
bldr tasks.remove_minion_key:my-project--my-environment`.
```

### Configure new nodes to be created

Remove or change:

- `ec2.ami` 

Removal works because the instance starts to inherit the value from `defaults`.

## Recreate node

- remove `ec2.suppressed`

Run `update_infrastructure` to recreate the node.

## Reinstate additional DNS

Bring back the original values for:

- `domain`
- `intdomain`

and run `update_infrastructure`.

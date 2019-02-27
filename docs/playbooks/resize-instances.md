# Resize instances without downtime

## Assumptions

- At least 2 EC2 nodes are used in a single stack.
- There is an ELB or another form of load balancer on top.
- The stack being modifies is called `my-project--my-environment`.
- The change is going from `t2.medium` to `t2.large`.

## Procedure (2 nodes)

### Remove additional DNS

Comment out:

- `ec2.dns-external-primary`
- `ec2.dns-internal`

from the project configuration, if present. 

After running `bldr update_infrastructure:my-project--my-environment,skip=ec2`, check that Route 53 does not have DNS entries left relating directly to EC2 instances.

### Destroy node 1

Add `ec2.suppressed` with the value `[1]`, and run `update_infrastructure,skip=ec2`.

To fully clear the existence of node 1, run also:
```
bldr tasks.remove_minion_key:my-project--my-environment`.
```

### Configure new nodes to be created with new size

Configuration change:

- `ec2.overrides.2.type` with the value `t2.medium` (the old type)
- change `type` with the value `t2.large` (the new type)

## Recreate node 1

- remove `ec2.suppressed`

Run `update_infrastructure` to recreate node 1.

### Destroy node 2

Add `ec2.suppressed` with the value `[2]`, and run `update_infrastructure,skip=ec2`.

To fully clear the existence of node 2, run also:
```
bldr tasks.remove_minion_key:my-project--my-environment`.
```

## Recreate node 2

- remove `ec2.overrides`
- remove `ec2.suppressed`

Run `update_infrastructure` to recreate node 2.

## Reinstate additional DNS

Uncomment:

- `ec2.dns-external-primary`
- `ec2.dns-internal`

and run `update_infrastructure`.

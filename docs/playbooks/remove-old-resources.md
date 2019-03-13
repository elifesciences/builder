# Remove old CloudFormation resources

Some stacks have CloudFormation resources follow an old naming format like `EC2Instance` (rather than `EC2Instance1`|`EC2Instance2`|..., introduced to allow multiple servers in the same stack). This format breaks `update_infrastructure` and blocks changes in any resource in the stack. 

To correct the situation, the `EC2Instance` resource and all its dependencies such as `ExtDNS`, `IntDNS`, etc. must be removed. It's feasible to preserve the CloudFormation template however, to avoid deleting other resources like RDS databases.

## Assumption

## Procedure

### Get the existing template

```
aws cloudformation get-template --stack-name elife-dashboard--ci | jq .TemplateBody | tee elife-dashboard--ci.json
```

### Clean the existing template

```
vim elife-dashboard--ci.json
```

Delete all `Resources` and `Outputs` that mention `EC2Instance`. Common examples:

- `EC2Instance`
- `ExtDNS`
- `IntDNS`

Never remove, if present:

- `AttachedDB` (RDS database which preserves state)

### Apply new template

The template needs to be on S3:

```
aws s3 cp elife-dashboard--ci.json s3://elife-builder/temporary-patches/elife-dashboard--ci.json
aws cloudformation update-stack --stack-name elife-dashboard--ci --template-url s3://elife-builder/temporary-patches/elife-dashboard--ci.json
```

### Check Route53 for orphan DNS entries and remove them

Open https://console.aws.amazon.com/route53/home and select the relevant hosted zones (`elifesciences.org`, `elife.internal`). Filter using the `subdomain` from `project/elife.yaml`.

For example, delete `ci--ppp-dash.elifesciences.org.` from the `elifesciences.org` hosted zone.

### Clean the Salt maste

To fully clear the existence of node 1, run also:

```
bldr tasks.remove_minion_key:elife-dashboard--ci
```

### Run `update_infrastructure`

```
./bldr update_infrastructure:elife-dashboard--ci,start=
```

The `start` parameter will avoid trying to start EC2 instances that are now missing.

This should ask you to confirm to create an `EC2Instance1` and other resources.

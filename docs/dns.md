# DNS

DNS entries for servers are maintained by builder for various cases.

All configuration fields described here relate to [project definitions](../projects/elife.yaml).

## External and internal

`External` DNS correspond to `*.elifesciences.org` entries, resolving to a public IP address and accessible over the public Internet.

`Internal` DNS entries correspond to `*.elife.internal` entries, resolving to a private IP address and accessible withing eLife's AWS VPC(s).

External entries need to be maintained upon servers being stopped, started or rebooted; the public IP addresses are reassigned. Internal entries do not need to, as the private IP addresses are static.

### HTTPS constraints

Practically all external DNS entries have the form of 3-level subdomains (`*.elifesciences.org`) to allow a wildcard certificate being used to implement HTTPS on them.

## Default entries

The `domain` and `intdomain` configuration fields respectively configure the presence of an external and internal DNS entry for the whole stack. They can be set to `false` to disable the creation of the entries.

The `subdomain` field provides a project-specific subdomain to use together with the environment name in these entries. For example, a subdomain like `profiles` will result in entries like `prod--profiles.elifesciences.org` and `prod--profiles.elife.internal` being created.

## CNAMEs

The `subdomains` field allow additional CNAMEs to be specified on a stack.

Specialized resources like `fastly` have their own way of specifying this, in this particular case a `cname` field.

## Multiple nodes

Multiple nodes in a cluster usually do not have individual DNS entries as they are hidden behind a load balancer.

These settings enable additional DNS entries:

- `ec2.dns-internal` allows the creation of internal DNS entries that can be used to make nodes in a cluster collaborate e.g. `prod--xpub--1.elife.internal`
- `ec2.dns-external-primary` allows the creation of a single external DNS entry for the [primary node](../docs/lingo.md) e.g. `end2end--xpub--1.elifesciences.org`

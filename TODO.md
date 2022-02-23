# TODO.md

This is just a scratchpad for keeping track of ideas, nice-to-haves, etc.

## done

* delete src/tests/fixtures/additional-projects
    - I think support for different regions and things has been removed
        - it was never really used

## todo

## todo (bucket)

* build_vars, are these supposed to look like that?
        "ext_node_hostname": "prod--alfred--%s.elifesciences.org",
        "int_node_hostname": "prod--alfred--%s.elife.internal",
* start/stop, I want to be able to start and stop individual nodes
    - ./bldr stop:iiif--prod--2
* ssh, when I specify a node for a non-clustered environment, it should give me a stacktrace
* handle all cases of BUILDER_NON_INTERACTIVE and get_input
* add a changelog and versioning and releases
* revisit tests
    - they take *forever*
* switch to threadbare
    - remove fabric
    - remove python2 support
* switch *away* from threadbare and fabric to something sane
    - with fewer dependencies
* revisit project configuration
    - config merging is painfully slow
    - 'aws' sections don't make a lot of sense now that resources across terraform and cloudformation are mixed
    - where to store unique per-instance non-templated configuration?
        - is this even the right place?
    - how to model new-instance vs existing-instance changes?
        - for example, new instances should get a ssd, old instances should continue using whatever
    - can project configuration be split from the code altogether?
        - we want to update project config and have it run through tests fast!
    - default resource blocks
        - so an ec2 instance is only present if an ec2 block is included
    - project config speccing
    - rip out caching
        - parsing/merging/validating little yaml/json files should be *quick*
* rename 'trop.py' to 'cloudformation.py'
* rename 'cfngen.py' to 'build_context.py' or something similar
* delete src/tests/fixtures/dummy-project2.yaml
    - looks like the pattern in tests/fixtures/dummy-project.yaml caught on instead

* if skip=ec2 in update_infrastructure, don't bring the nodes into a running state
    - this may actually interfere with IP addresses in the cloudformation template
        - in which case, what depends on those values? surely they would get old/stale quickly ...
* projects, removing caching 

# upgrading Salt

**warning!:** Salt may not be following semantic versioning. Assumptions about non-breaking changes in 'patch' versions could be dangerous.

The process follows this pattern:

1. examine the CHANGELOG for the desired Salt version and all versions in between it and the current Salt version
2. change the `salt` version in `./projects/elife.yaml` under the `defaults` section (very top of file)
3. examine any per-project overrides of the `salt` version and update as necessary
4. check for any breaking changes in formulas
5. open a PR, get sign off, merge
6. update master
7. update minions

## 1. examine the Salt CHANGELOG

Very important but also very tedious if there are a large number of changes.

Keep an eye out for any breaking changes, changes in behaviour, deprecations.

Historically we haven't had problems jumping several 'patch' versions at once.

## 2. update the Salt version in projects file

Straightforward. It lives at the top of the projects file at `defaults.salt`.

Make sure the version you want to upgrade to is available via salt-bootstrap and compatible with your os/distribution.

## 3. per-project Salt version overrides

In some cases a project may be using a different version of Salt from the default.

This is rare and there should always be a clear reason for the override.

Ideally your change encompasses theirs.

## 4. check for breaking changes in formulas

If something jumped out at you in step 1, grep for cases via github or in your ./cloned-projects directory. 

Test it by bringing up a vagrant or masterless instance.

The `heavybox` project may encounter your problem and provide feedback.

## 5. open a PR, get sign off, merge

The CI process will *not* confirm the correctness of your Salt version changes. A green build here means nothing.

The purpose of the CI process is to test for regressions in formula changes as run on the _current_ Salt version.

## 6. update master

The `master-server` project must always be running the same or a later version of Salt than the minions it controls.

The installed version of Salt is updated using Builder's `master.update_salt` command:

    $ ./bldr master.update_salt:master-server--instance
    
For example:

    $ ./bldr master.update_salt:master-server--2018-04-09-2

## 7. update minions

Minions are updated the same way as the master server, except you probably have a ~100 cases to handle:

    $ ./bldr master.update_salt:project--instance

At the time of writing there is no automated solution to updating the installed version of Salt.

Notes:

* New **warnings** in the Salt `highstate` may appear, announcing deprecations. These can be fixed per-project later.



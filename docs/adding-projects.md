# adding projects

What must be done to use the `builder` with your own projects?

## project formula

The builder requires all projects to adhere to a certain directory structure. The `builder-example-project` can be found [here](https://github.com/elifesciences/builder-example-project).

Essentially, everything the `builder` needs is contained within the `salt` directory. This structure makes what SaltStack calls a *formula*. Examples of other, official, formulas can be found [here](https://github.com/saltstack-formulas).

Your actual project can continue living at the root of the repo (so long as it doesn't use the `salt` directory for it's own purposes) *or* your project can live in it's own repository completely separate from the formula.

> This doc won't go into how to use Salt and assumes from here on out you have a well formed project formula.

## builder project file

`builder` comes with two 'project' files. These files list the projects made available by the organisation. Your project will need an entry in here.

> If you don't have a project file yet, copy the `example.yaml` file and replace the settings for `project1` with your own.

Your project entry requires a `formula-repo` key whose value should be a path to the git repository your project formula lives in.

Much more detail about the project file can be found [here](docs/projects.md).

## Vagrant

You can now bring up instances of your project with:

	vagrant up

and choosing your project from the list, or

	PROJECT=yourprojectname vagrant up

to avoid the menu.

## AWS

Vagrant runs within a masterless environment without the organisation's secret credentials. This makes it very easy to simply clone (using the `formula-repo` value) and provision.

To deploy your application to AWS however requires a few more steps.

In your `builder-private` repository ([example here](https://github.com/elifesciences/builder-private-example)):

1. add your project to the list of [`gitfs_remotes`](https://github.com/elifesciences/builder-private-example/blob/master/etc-salt-master#L49)
2. update the *state* [`top.sls`](https://github.com/elifesciences/builder-private-example/blob/master/salt/top.sls) file with the contents of your `example.top` file.
3. if necessary, update the *pillar* [`top.sls`](https://github.com/elifesciences/builder-private-example/blob/master/pillar/top.sls) with an entry for your pillar file.
4. if step 3, then drop a copy of your `example.pillar` file into the [`./pillar/` directory](https://github.com/elifesciences/builder-private-example/tree/master/pillar).

Then update your `master-server` project instance with:

	./bldr update_master

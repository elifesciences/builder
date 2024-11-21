# dev-salt

This directory is used to allow overriding of the salt dev environments created and used by the ./create-dev-env

When a project dev env is created using that script, a corresponding set of directories are created here under the name of the project.

For example, if you are created a dev environment for a project called `iiif`, there would be a directory here called `iiif`, with a `pillar` and `salt` diretory that would take precendence over the project, dependant and base formulas within that environments. This allows you to experiment with alternative configs, pillar data, etc without having to make those in the clone-project formulas and risk committing them accidentally.

This whole directory is gitignored and beyond the creation of the directories as described above, you should manage its contents yourself.

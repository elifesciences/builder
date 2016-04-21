# Continuous Deliveyr (CD)

This article concerns `elife-builder`, `builder-core` and the `elife-ci` 
environment.

## build vars

Part of Continuous Delivery is to deploy the latest code of a particular branch,
but how do we tell AWS and SaltStack what the parameters of the build were?

eLife tests and deploys using Jenkins. It's not the perfect solution, but it is
very robust, well supported by the community and extremely flexible. We can do
a lot with this tool.

Jenkins has a `git` plugin that will export build parameters as environment 
variables. `builder-core` captures some of these environment variables and
puts them in a json file called `/etc/build_vars.json`. The structure of this
file looks like:

    {project-name: {branch: foo, revision: bar}}

for example:

    {elife-website: {branch: master, revision: head}}

The code for the above is [here](https://github.com/elifesciences/builder-core/blob/master/buildercore/trop.py#L52)

Salt will then [look for this file](https://github.com/elifesciences/elife-builder/blob/master/salt/salt/_modules/elife.py) 
during configuration and, if it exists, read those values and make them 
available in the pre-processing context.

In the state file you have to access those variables as: 

    {{ salt['elife.project']()[project-name][value] }}
    
For example:

    {{ salt['elife.project']()['elife-website']['branch'] }}
    
The `salt['elife.project']()` is calling the function `project` in the module 
`elife` accessed via the `salt` global variable. This function call returns the
data structure `{elife-website: {branch: master, revision: head}}`
    


## Deletion policy

Automatically created stacks are given a default expiry date of __two weeks from today__.

Automatically created stacks are deleted if __their expiry date is in the past__.

__Any__ running stack (provisioned by elife-builder) can have it's expiry date 
arbitrarily extended.

# debugging elife-builder

The elife-builder is a python application. It isn't particularly sophisticated 
with little magic involved. Standard debugging techniques apply.

Complexity and uncertainty arise from the libraries it heavily relies upon, such 
as Boto and Fabric.

# Python errors

Python will give a stacktrace when an error originating from it occurs. 

The two major culprits the problem almost certainly lives in are within the 
elife-builder's Fabric tasks (inside `src/`) and within the `builder-core` 
repository.

## builder-core

`builder-core` used to live within elife-builder but once established rarely 
changed. I felt prudent to keep this code seperate from the rapidly changing 
interface concerns and secrets within the elife-builder. 

If you are:

* talking to AWS
* creating an AMI
* generating a stack template

Then the problem has a high chance of being in the `builder-core` repo.

Timeouts and remote state handling are currently handled poorly, usually with a 
dumb polling waiting until something _isn't_.

## elife-builder Fabric tasks

The `bldr` script is just a thin wrapper around a Fabric `fabfile` and the 
`fabfile` simply includes modules from the `./src/` directory.

Fabric tasks form the elife-builder interface with the majority of logic living 
in the original `cfn.py` file. New code tends to be added directly to this file 
and organised into different modules later on. 

It calls and relies heavily upon the code in `buildercore.*`, doing very little 
'business logic' itself. 

Errors here in the interface are easier to debug as the stack is shallow.

# Salt Stack errors

## Failed states

After Salt has finished provisioning it will give you a summary of the number of 
successfully enforced and failed states. Ideally there should be __zero__ failed 
states. A big part of my job is debugging why a state failed and figuring out 
methods to ensure the jigsaw pieces are properly placed.

[TODO: examples!]

## Syntax errors, broken logic

Sometimes Salt won't be able to complete provisioning because of a syntax error, 
broken state or recursive requisite and it halts and exits upon encountering it.

These problems are typically very easy to find as they relate to code you're 
currently working on and broke so hard and so fast they rarely make it into a 
commit.

[TODO: examples!]

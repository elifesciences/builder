This is the "top-level directory" for the `simple-project` Salt formula.

Within this directory we expect all Salt configuration for `simple-project` 
to exist.

This keeps build configuration separate from any other type of build configuration 
(like Docker/Chef/Ansible).

The `pillar.example` file contains the variables this project needs to 
configure itself.

The salt states take the values in the pillar file and uses them when rendering 
the state files and templates in the `simple-project` directory.

Builder will use the `pillar.example` file and *any other pillar data* it can find
when provisioning your application, including it's own private versions of your
expected values. 

As a project maintainer, your only responsibility is that the 
`pillar.example` file accurately reflects what your application requires.

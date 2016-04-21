# Lagotto

__This doc describes how `Lagotto` is used within the elife-builder project.__

Official Lagotto documentation can be found [here](https://github.com/articlemetrics/lagotto/).

Lagotto provides methods to install via Vagrant and Chef and Capistrano. This
project uses a mixture of Salt and [Capistrano](https://github.com/articlemetrics/lagotto/blob/master/docs/deployment.md) 
to deploy Lagotto.

## Futon

Futon is a web GUI for CouchDB and is available within vagrant on port `5984`.

## Restoring legacy backups

Database restoration is intended only as part of the initial build.

### mysql 

Salt will look in `/srv/public` for a database called `alm.mysql.sql` and, if 
found, will drop the existing database (__no backup__) and load the new one.

### couchdb

Salt will look in `/srv/public` for a database called `alm.couchdb.couch` and, 
if found, will copy the file to `/var/lib/couchdb/lagotto.couch`, 
__overwriting__ any existing file.

## Custom rake tasks

Rake is a means of writing quick tasks in Ruby, a bit like Fabric for Python.

There are now four custom rake tasks:

* `lagotto:create_admin` creates a user with an "admin" role.
* `db:sources:decrates` reduces the :rate_limiting by a factor of 10
* `db:sources:incrates` increases the :rate_limiting by a factor of 10
* `db:sources:alter` allows one to alter attributes of a `Source` object.

### decrates & incrates

Used in non-production environments to limit how often calls can be made to 
services so that they don't interfere (too much) with the production environment.

### db:sources:alter

This command isn't being used currently and I've artificially limited the 
attributes it can modify to just `rate_limiting`. I see this command being 
useful in the future to fine-tune the rate_limiting of individual `Source`s.

# elife-api

__This doc describes how the eLife API is used within the elife-builder 
project.__

The `elife-api` project is eLife's central point for talking to other services.

## Proxied requests

Because we only want to talk to elife-api and because sometimes we have other
applications with their own REST interfaces, we need to have those requests 
proxied to those other downstream applications.

### Lax

Another of eLife's projects is `Lax`, an article data repository with it's own
REST interface. This interface can be accessed from the `elife-api` via the path
`http://api.elifesciences.org/proxy/lax/...`. 

[This proxying is done using Nginx](https://github.com/elifesciences/elife-builder/blob/master/salt/salt/elife-api/config/etc-nginx-sitesavailable-elifeapi.conf#L19).

At this moment the Swagger interface to the API is broken. I'm not sure if there 
will be time to fix this, but the API calls themselves should still work.


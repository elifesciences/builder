# elife-api

__This doc describes how the Lax is used within the elife-builder 
project.__

Lax is an article data store that we intend to provide an interface to for the 
public via the elife-api.

Deployed in production I expect it to have it's own server and internal access 
only via the VPC (Virtual Private Cloud) *except* for it's API, which the 
`elife-api` project proxies to. This means anything outside of the API prefix 
`/api/` will be unavailable to the public (`/admin` for example). 

The `elife-api` is using a crazily long and random username and password for 
BASIC authentication for non-GET requests to the API. 


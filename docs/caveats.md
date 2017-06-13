# CAVEATS

This is a list of hassles and annoyances that need to be automated/removed/cleaned up/something because they bother me.

1. creating a master requires a token to clone the builder-private repo
	- this token requires a public key
    	- upload private key to root user [done]
    	- generate a pub key [done]
    	- create a github deploy key **[todo]**

2. builder-private salt top.sls file must be kept synchronised with individual projects
	- might be solvable with dynamic top files

3. builder-base-formula pillar must be kept synchronized with the builder-private elife pillar
	- not sure if there is a way around this one
	- could compare data structures if nothing else to detect missing keys/irregularities


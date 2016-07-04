# CAVEATS

This is a list of hassles and annoyances that need to be automated/removed/cleaned up/something because they bother me.

1. creating a master requires a token to clone the builder-private repo
	- this token requires a public key
    	- upload private key to root user [done]
    	- generate a pub key [done]
    	- create a github deploy key **[todo]**

2. builder-private salt top.sls file must be kept synchronised with individual projects
	- might be solvable with dynamic top files

3. builder-private pillar data is not always being updated
	- problem with lock files?
	    - https://github.com/saltstack/salt/issues/32888
	- possibly problem with minion cache
	    - https://github.com/saltstack/salt/issues/24050
	- probably *also* waiting for refresh interval of ~60 seconds

4. builder-base-formula pillar must be kept synchronized with the builder-private elife pillar
	- not sure if there is a way around this one
	- could compare data structures if nothing else to detect missing keys/irregularities

5. master rejects minion keys if one already exists
	- this can be solved by running this on master
	    - salt-key -d minionid
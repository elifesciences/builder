# Running on OSX

Due to the underlying dependencies, it can be a bit hit and miss using `builder` on OSX. This can be worked around by running `builder` inside a container with the correct dependencies installed.

```
./container.sh
```

Once started...

```
./update.sh --exclude virtualbox
```

Depending on the commands you intend to run, you might also need to login into `vault`.

```
./bldr vault.login
```

You should then be able to run any command you need to.

If you use a different SSH key, or your AWS credentials are stored in a non-standard location then use the `CUSTOM_SSH_KEY` and `CUSTOM_AWS_CREDENTIALS` environment variables to point at the right files, e.g.

```
CUSTOM_SSH_KEY=/path/to/ssh/key CUSTOM_AWS_CREDENTIALS=/path/to/aws/credentials/file ./container.sh
```
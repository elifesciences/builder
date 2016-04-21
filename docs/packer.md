# Packer

Packer is used to generate Vagrant baseboxes and the plugin `vagrant-s3auth` is
used to allow us access to these boxes stored in our S3 bucket.

Code used for taking advantage of packer lives in `src/packer.py` and it's tasks
are those prefixed with `packer.` given ./bldr -l

All projects use the `elifesciences/basebox` unless there is significantly more
to do (elife-website) in which case it get it's own basebox. Each box has to be
downloaded from S3 and each box is about 4GB.

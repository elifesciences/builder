elife-builder && logrotate

Unconstrained growth of log files is a problem waiting to happen.

[Logrotate](http://linuxcommand.org/man_pages/logrotate8.html) allows us to describe what we want to happen to certain files as they grow.

Logrotate is installed as part of the base system and can be configured simply by placing definitions in the `/etc/logrotate.d/` directory.

These definitions looks like:

    /var/log/apache2/error.log {
        rotate 2
        missingok
        compress
        size=1M
    }

Dead simple.

All options are documented in the man pages with `man logrotate` or online: http://linuxcommand.org/man_pages/logrotate8.html

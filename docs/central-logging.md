# central-logging

The central logging server is a complex beast.

_Briefly_: individual servers gather data about themselves and the programs 
running on them. This data is sent to the logging server. The logging server 
receives all this mixed data and attempts to turn it into structured data before
sending it to other programs that make use of structured data for monitoring, 
reporting, alerting, graphing, etc.

## collectd

Collects system metrics like cpu/disk/memory/network stats on minions and sends
them to the collectd instance listening on the logging server (bypassing 
syslog-ng).

## syslog-ng

A sophisticated syslog implementation that allows the filtering, transformation 
and muxing of streams of log entries to different destinations, like other log 
files, remote servers, etc. syslog-ng runs on minions and they send their data
to the syslog-ng on the logging server.

syslog-ng on the logging server is responsible for sending (or not) data 
downstream to other applications like riemann and elasticsearch.

## patterndb

patterndb is part of the syslog-ng project and is a means of parsing and 
extracting structured data from log entries. It doesn't use regular expressions,
but a simpler format of regular types (string, float, etc) and a search method 
called "longest prefix match radix tree" to find the correct pattern to extract 
the data. This data is then available in the syslog-ng environment to use when
determining what goes downstream and how.

## riemann

Riemann is a realtime stream processor. Data sent to Riemann is in a simple
format with a few mandatory fields and an arbitrary number of additional fields.
One of the fields is `TTL` which tells Riemann how long to hang on to the 
record. Riemann *is not* a long term storage mechanism.

The stream of data entering Riemann can be broken down into sub-streams and
include filtering, transformation, aggregation, sending alerts, etc.

## riemann-dash

Riemann-dash is a dashboard for Riemann, it has it's own configuration language 
for controlling what is displayed within it's widgets. 

## elasticsearch

Elasticsearch is a search engine derived from lucene and solr and is another
downstream destination for parsed log entries emanating from syslog-ng.

### browsing, searching

A plugin called `elasticsearch-head` is installed that appears to be the least 
crap of a [half-dozen offers available](http://www.elasticsearch.org/guide/en/elasticsearch/client/community/current/front-ends.html).
You can access it at `http://localhost:9200/_plugin/head/` on your dev machine.

## kibana

Kibana is a powerful visualisation tool for Elasticsearch.

# Patterndb 

Notes for creating new patterns with patterndb.

### Step 1: test if your pattern already exists and is handled by patterndb with 
`pdbtool match -M "<log message here>"` or 
`pdbtool match -f /var/log/yourlogfile.log`. 

If you get something like:

    .classifier.class=unknown
    TAGS=.classifier.unknown

Then nothing was found. To see what happens when a pattern is found, try this:

    pdbtool match -M '10.0.2.2 - - [19/Dec/2014:13:44:30 +0000] "GET /sources HTTP/1.1" 404 151 "-" "Opera/9.80 (X11; Linux x86_64) Presto/2.12.388 Version/12.16"'

Which should yield something similar to:

    MESSAGE=10.0.2.2 - - [19/Dec/2014:13:44:30 +0000] "GET /sources HTTP/1.1" 404 151 "-" "Opera/9.80 (X11; Linux x86_64) Presto/2.12.388 Version/12.16"
    .classifier.class=system
    .classifier.rule_id=9e2a32a4-36bc-4cb6-b32f-8b19be355393
    httpd.request.clientip=10.0.2.2
    httpd.request.username=-
    httpd.request.finishtime=19/Dec/2014:13:44:30 +0000
    httpd.request.type=GET
    httpd.request.url=/sources
    httpd.request.protocol=HTTP/1.1
    httpd.request.statuscode=404
    httpd.request.size=151
    httpd.request.referrer=-
    httpd.request.useragent=Opera/9.80 (X11; Linux x86_64) Presto/2.12.388 Version/12.16
    http.request.ident=-
    TAGS=.classifier.system

### Step 2: create a pattern if your log format is not matched

This will create a template for you:

    echo 'yourlogmessagehere' | pdbtool patternize -p - > new_pattern.xml

The pattern generated will simply match _exactly_ what you gave it - not too 
useful.

The docs regarding patterns can be [found here](https://www.balabit.com/sites/default/files/documents/syslog-ng-ose-3.4-guides/en/syslog-ng-ose-v3.4-guide-admin/html-single/index.html#reference-parsers-pattern-databases).

Example patterns can be [found here](https://github.com/balabit/syslog-ng-patterndb).

__TODO: bit about how these patterns work, capture groups__

Once your pattern has been updated to match things, you can test the validity 
with `pdbtool test --validate elife_app.conf` or by using the `match` command 
like above but only specifying your new pattern file: 

    pdbtool match -M '10.0.2.2 - - [19/Dec/2014:13:44:30 +0000] "GET /sources HTTP/1.1" 404 151 "-" "Opera/9.80 (X11; Linux x86_64) Presto/2.12.388 Version/12.16"' -p new_pattern.xml

All xml files within /etc/syslog-ng/patterndb.d/ will be compiled into the 
global pattern file used by syslog. It can be forced to run with the following 
command:

    # pdbtool merge -r --glob *.xml -D /etc/syslog-ng/patterndb.d/





# NuoDB Collector Daemon

The NuoDB collector daemon is the replacement for NuoCA.

# Introduction

Most modern application monitoring systems consist of the following 3
core components:

. Collector             — daemon(s) to gather metrics
. Time Series database  — for storage of real-time, high volume metrics
. Query & Visualization — that enables queries and display charts to
                          understand metrics

This docker image is a Collector daemon utilizing a popular collector -
telegraf. It's designed to be used as a sidecar with a NuoDB engine
container to collect metrics from the engine and publish those metrics
to a time series database or some other output destination.

Built into this container are 4 input plugins to collect metrics from
the engine:

1.  metrics - collects the stats published by `nuocmd get_stats`  on a
    regular 10s interval.
2.  msgtrace - performs a message trace query every interval (30s) and
    outputs delta between the previous interval.
3.  synctrace - performs a sync trace query every interval (30s) and
    outputs delta between the previous interval.
4.  threads - periodically looks at /proc/$(pidof nuodb)/tasks/*/stats
    to collect metrics on cpu usage for each thread of the nuodb
    process.

The default output plugin is to an influxdb time series database(s).

Telegraf includes a set of builtin inputs and outputs that can also be
used.  When using this container as a sidecar these plugins are
controlled via configmaps that are mounted into the container
dynamically and thus, can be easily be modified and configured.

# Building

When building this image,  it should be tagged as registry/nuodb/nuocd:tag

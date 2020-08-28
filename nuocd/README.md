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
dynamically and thus, can easily be modified and configured.

# Building

When building this image,  it should be tagged as registry/nuodb/nuocd:tag

# Using as Sidecar

The use of this container is as a sidecar in the
nuodb-helm-charts/stable/database or nuodb-helm-charts/stable/admin.
In order to see how to configure the sidecar see those helm charts.

# Setup on bare metal

To setup the collector on bare metal.  The following steps can be
done.

0) dependencies

pidof - installed - sysvinit-tools package
python2.7


1) Download and install telegraf.

wget https://dl.influxdata.com/telegraf/releases/telegraf-1.15.2-1.x86_64.rpm
sudo yum localinstall telegraf-1.15.2-1.x86_64.rpm

* for other platforms see:
- https://portal.influxdata.com/downloads/

2) Install nuocd directory

cp -r nuocd /opt/.

3) download pip - iff it does not already exist

curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py

4) download python requirements

pip install -r requirements.txt -t /opt/nuocd/pylib

4) Configure telegraf

sudo cp conf/nuodb.conf /etc/telegraf/telegraf.d
sudo cp conf/outputs.conf /etc/telegraf/telegraf.d
sudo edit /etc/telegraf/telegraf.conf
 -- comment out the default [[outputs.influxdb]] section
sudo chown -R telegraf.telegraf /etc/telegraf
sudo cat >> /etc/default/telegraf <<EOF
INFLUXURL=http://<hostinflux>:8086
PYTHONPATH=/opt/nuocd/pylib
EOF

5) restart telegraf

sudo systemctl daemon-reload
sudo systemctl restart telegraf

NOTE:

If not starting telegraf via systemd then the variables set in
/etc/default/telegraf are not picked up automatically.  Instead you
can start telegraf with the following command:

sh -c "$(cat /etc/default/telegraf | tr '\n' ' ') telegraf --config /etc/telegraf/telegraf.conf --config-directory /etc/telegraf/telegraf.d"

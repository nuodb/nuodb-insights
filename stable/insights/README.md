# Influx/Grafana/NuoCA Helm chart

## Description

This helm3 chart will deploy the grafana dashboards and datasources to
display nuodb metrics stored in influxdb (in database nuodb).
Optionally the chart can deploy grafana, influxdb, and nuoca
instances.   If an existing grafana instance exist, the dashboards can
be labelled such that that instance can retrieve (with the dashboard
sidecard) the dashboards.   

## Deploying

In order to use this helm chart locally you will need to first update
the dependencies.

```
$ cd monitoring-influx
$ helm dep update
```

## Installing

The helm chart consist of three subcharts which can selectively be disabled.

```
grafana:
  enabled: true
influxdb:
  enabled: true
nuoca:
  enabled: true

By default, if the grafana chart is enabled a sidecar is created to
collect the dashboards and datasource configmaps.  The dashboards will
be deployed to grafana in the nuodb folder for ordId 1.

Likewise by default,  if the influxdb chart is enabled an initscript
is created that will initialize an influxdb database named nuodb.








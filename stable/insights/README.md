# NuoDB Insights Helm Chart

## Description

This helm3 chart will deploy the grafana dashboards and datasources to display nuodb metrics stored in influxdb (in database nuodb).
Optionally the chart can deploy grafana and influxdb instances.
If an existing grafana instance exist, the dashboards can be labelled such that that instance can retrieve (with the dashboard sidecard) the dashboards.   

## Install Dependencies

In order to use this helm chart locally you will need to first update
the dependencies.

```
$ cd monitoring-influx
$ helm dep update stable/insights
```

## Command

```
helm install stable/insights [--generate-name | --name releaseName] [--set parameter] [--values myvalues.yaml]
```

## Grafana Default Password
By default, Grafana generates a random password when the instance is started.
To retrieve the password, you can read the Kubernetes secret as such:
```
kubectl get secret <grafana-secret-name>  -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
```


## Installing the Chart
All configurable parameters for each top-level scope are detailed below, organized by scope.

### grafana.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `enabed` | Enable the 3rd party Grafana Installation | `true` |

### influxdb.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `enabed` | Enable the 3rd party InfluxDB Installation | `true` |

### config.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `grafana.enabled` | Load NuoDB Dashboards on start | `true` |

By default, if the grafana chart is enabled a sidecar is created to collect the dashboards and datasource configmaps.
The dashboards will be deployed to grafana in the nuodb folder for ordId 1.

Likewise by default, if the influxdb chart is enabled an initscript is created that will initialize an influxdb database named nuodb.







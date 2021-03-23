# NuoDB Insights Helm Chart

## Description

This chart starts a NuoDB Insights deployment on a Kubernetes cluster using the Helm package manager.

## Software Version Prerequisites

| Software   | Release Requirements                           | 
|------------|------------------------------------------------|
| Kubernetes |  The latest and previous minor versions of Kubernetes. For example, if the latest minor release of Kubernetes is 1.16 then 1.16 and 1.15 are offically supported. Charts may still work on previous versions of Kubernertes even though they are outside the target support window. To provide that support the API versions of objects should be those that work for both the latest minor release and the previous one.|
| Managed Kubernetes Distributions |  OpenShift 4.x, Google GKE, Amazon EKS, Azure AKS, or Rancher RKE. Charts may also work on other Kubernetes distributions. The distributions listed here are tested regularly. |
| Helm       |  Version 3 is supported. v3.2 is the main development environment   |
| NuoDB      |  Version [4.0.4](https://hub.docker.com/r/nuodb/nuodb-ce/tags) and onwards. |
| NuoDB Helm | NuoDB Helm Charts [3.0.0](https://github.com/nuodb/nuodb-helm-charts) or newer |

## Command

```
helm install [name] nuodb-insights/insights [--generate-name] [--set parameter] [--values myvalues.yaml]
```

## Installing the Chart

All configurable parameters for each top-level scope are detailed below, organized by scope.

### grafana.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `enabled` | Enable the 3rd party Grafana Installation | `true` |

For a complete list of configuration variables supported by the 3-rd party chart refer to [Grafana Helm Chart](https://github.com/grafana/helm-charts/tree/main/charts/grafana).
By default, if the grafana chart is enabled a sidecar is created to collect the dashboards and datasource configmaps.
The dashboards will be deployed to grafana in `/var/lib/grafana/dashboards/nuodb` and `/var/lib/grafana/dashboards/nuodb` directories with `orgId` of 1.

### influxdb.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `enabled` | Enable the 3rd party InfluxDB Installation | `true` |
| `host` | InfluxDB FQDN in case it is installed in different namespace | `nil` |
| `port` | InfluxDB port in case it is installed in different namespace | `8086` |

For a complete list of configuration variables supported by the 3-rd party chart refer to [InfluxDB Helm Chart](https://github.com/influxdata/helm-charts/tree/master/charts/influxdb).
By default, if the influxdb chart is enabled `init-nuodb.sh` is created that will initialize all InfluxDB databases used by NuoDB Insights.

### insights.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `grafana.enabled` | Load NuoDB Dashboards on start | `true` |
| `nuocollector.enabled` | Create NuoDB collector output plugin for InfluxDB | `true` |


## Uninstalling the Chart

To uninstall/delete the deployment:

```bash
helm delete <releaseName>
```

The command removes all the Kubernetes components associated with the chart and deletes the release.

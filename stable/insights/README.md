# NuoDB Insights Helm Chart

## Description

This chart starts a NuoDB Insights deployment on a Kubernetes cluster using the Helm package manager.

## Software Version Prerequisites

| Software   | Release Requirements                           | 
|------------|------------------------------------------------|
| Kubernetes |  1.15 or newer |
| Managed Kubernetes Distributions |  OpenShift 4.x, Google GKE, Amazon EKS, Azure AKS, or Rancher RKE. Charts may also work on other Kubernetes distributions. The distributions listed here are tested regularly. |
| Helm       |  Version 2 and 3 are supported, v2.9 or greater. v3.2 is the main development environment   |
| NuoDB      |  Version [4.0.4](https://hub.docker.com/r/nuodb/nuodb-ce/tags) and onwards. |
| NuoDB Helm | NuoDB Helm Charts [3.0.0](https://github.com/nuodb/nuodb-helm-charts) or newer |

## Command

```
helm install nuodb/insights [--generate-name | --name releaseName] [--set parameter] [--values myvalues.yaml]
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

By default, if the grafana chart is enabled a sidecar is created to collect the dashboards and datasource configmaps.
The dashboards will be deployed to grafana in the nuodb folder for ordId 1.

### influxdb.*

| Parameter | Description | Default |
| ----- | ----------- | ------ |
| `enabed` | Enable the 3rd party InfluxDB Installation | `true` |
| `host` | FQDN of InfluxDB in case it is installed in different namespace | `nil` |


By default, if the influxdb chart is enabled an initscript is created that will initialize an influxdb database named nuodb.

### config.*

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

### The instructions on this page are in three parts:

1. **[Getting Started with Helm][4]** describes how to install and configure Helm on a client host. 
2. **[Deploying NuoDB using Helm Charts][5]** contains a quick primer on how to deploy the NuoDB Helm Charts.
3. **[Deploying NuoDB Insights using Helm Charts][9]** describes how to install NuoDB Insights.


# Getting Started with Helm 

If using Red Hat OpenShift, confirm the OpenShift `oc` client program is installed locally and that you are logged into your OpenShift instance.

## Install Helm 3

If you are planning to install Helm 2, please follow the [official Helm 2 docs][7].

### MacOS

Use the Brew Package manager.
```
brew install helm
```
### Linux

Every [release][2] of Helm provides binary releases for a variety of OSes. 

1. Download your [desired version][2]
2. Unpack it (`tar -zxvf helm-${helm-version}-linux-amd64.tgz`)

This example uses Helm version 3.2.4, which can be downloaded via <https://github.com/kubernetes/helm/releases/tag/v3.2.4>.

Run the following commands to install the Helm locally on your Linux client machine:
```bash
$ curl -s https://storage.googleapis.com/kubernetes-helm/helm-3.2.4-linux-amd64.tar.gz | tar xz
$ cd linux-amd64
```

Move the Helm binaries to /usr/local/bin
```
$ mv helm /usr/local/bin
```

## Confirm that the Helm client is installed correctly 

The results should be as follows:

```bash
helm version
version.BuildInfo{Version:"v3.2.4", GitCommit:"0ad800ef43d3b826f31a5ad8dfbb4fe05d143688", GitTreeState:"dirty", GoVersion:"go1.14.3"}
```

# Deploying NuoDB using Helm Charts

The minimal supported version of NuoDB and the NuoDB helm charts is specified in the [Insights Helm Chart Readme](insights/README.md).

For steps to install the NuoDB database please read the documentation in the [NuoDB Helm Charts][8] repository.
The [Admin Chart](https://github.com/nuodb/nuodb-helm-charts/tree/master/stable/admin) and the [Database Chart](https://github.com/nuodb/nuodb-helm-charts/tree/master/stable/database) must be installed with `nuocollector.enabled` set to `true`.

# Deploying NuoDB Insights using Helm Charts

## Configuration Parameters

The `insights` Helm Chart has a default [`values.yaml`](insights/values.yaml) parameter file that contains configuration parameters specific to that chart.
For configuration options please see the [Insights Helm Chart Readme](insights/README.md).

## Deployment Steps

The installation of the [`NuoDB Helm Charts`][8] and [`NuoDB Insights`](insights) can occur in an order.

### Installing a released version of NuoDB Insights

The default repository for NuoDB is located at https://nuodb.github.io/nuodb-helm-charts and must be enabled.

To add the charts for your local client, run the `helm repo add` command below:

```
helm repo add nuodb-insights https://nuodb.github.io/nuodb-insights
"nuodb-insights" has been added to your repositories
```

To confirm the NuoDB Insights chart has been added to your local chart repository, run 
```
helm search repo nuodb-insights
```

Install the chart:
```
helm install [name] nuodb-insights/insights [--generate-name] [--set parameter] [--values myvalues.yaml]
```
For the name, use `insights` and for the namespace use `nuodb` : 
```
helm install insights nuodb-insights/insights --namespace nuodb
```

### Installing from source

Clone NuoDB Insights and cd into it:
```
$ git clone https://github.com/nuodb/nuodb-insights
$ cd nuodb-insights
```

In order to use this helm chart locally you will need to first update the dependencies:
```
$ helm dep update stable/insights
```

Install the chart:
```
helm install [name] stable/insights [--generate-name] [--set parameter] [--values myvalues.yaml]
```

### Grant Red Hat OpenShift privileges

By default Grafana deployment will run as user, group and fsGroup of 472. The value can be configured in `grafana.securityContext`.
Unless a Security Context Constraint is created to allow that, Ret Hat OpenShift won't start Grafana container.
If [NuoDB SCC][10] has been created already in the cluster, it can be modified and assigned to the service account used by Grafana. Otherwise new Security Context Constraint needs to be created.

Specify the name of the Grafana service account during NuoDB Insights installation:

```bash
helm install insights nuodb-insights/stable/insights -n nuodb \
  --set grafana.serviceAccount.create=true \
  --set grafana.serviceAccount.name=grafana
```

Patch NuoDB SCC so that 472 fsGroup is allowed and assign it to the service account set in the above command.

```bash
kubectl patch -n nuodb scc nuodb-scc --type='json' \
  -p='[{"op": "replace", "path": "/fsGroup", "value":{"type": "MustRunAs", "ranges": [{"max": 472, "min": 472}] } }]'
oc adm policy add-scc-to-user nuodb-scc system:serviceaccount:nuodb:grafana -n nuodb
```

### Installing in different namespace

If NuoDB Insights is installed in the same namespace with NuoDB database, no additional steps are needed.
Otherwise, it is required to create NuoDB Collector configuration for Insights in all namespaces where NuoDB admin and database services are running. This can be done by installing the chart and setting `insights.influxdb2.host` to the InfluxDB fully qualified domain name. For example:

```bash
helm install insights nuodb-insights/insights -n nuodb \
  --set grafana.enabled=false \
  --set influxdb2.enabled=false \
  --set insights.grafana.enabled=false \
  --set influxdb2.host=<InfluxDB FQDN> \
  --set insights.nuocollector.enabled=true
```

## Accessing NuoDB Insights

By default, the NuoDB Insights Grafana dashboard WebUI will be available within the Kubernetes cluster via ClusterIP service. One way to access the WebUI dashboards is to use port forwarding and navigate your web browser to http://localhost:8080/.

```
kubectl port-forward service/insights-grafana 8080:80
```

Grafana 3rd party chart supports ingress with Grafana 6.3 and above. Configure ingress during NuoDB Insights chart installation and navigate to one of the hosts specified in `grafana.ingress.hosts` variable.
For example:

```
helm install insights nuodb-insights/insights -n nuodb \
  --set grafana.ingress.enabled=true \
  --set grafana.ingress.hosts='{"insights.example.com"}'
```

For Red Hat OpenShift deployments the service can be exposed via route.

```
oc expose svc/<release-name>-grafana
```

### Grafana Default Password

By default, Grafana generates a random password when the instance is started.
To retrieve the password, run:
```
kubectl get secrets -n nuodb \
  $(kubectl get secrets -l app.kubernetes.io/name=grafana -n nuodb -o custom-columns=":metadata.name" --no-headers=true) \
  -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
```

## Cleanup

See the instructions for the `insights` chart for deleting the applications.
An alternative cleanup strategy is to delete the entire project:

`kubectl delete namespace nuodb`

[1]: https://helm.sh/docs/using_helm/
[2]: https://github.com/helm/helm/releases
[4]: #getting-started-with-helm
[5]: #deploying-nuodb-using-helm-charts
[6]: https://github.com/nuodb/nuodb-helm-charts#software-release-requirements
[7]: https://v2.helm.sh/docs/using_helm/
[8]: https://github.com/nuodb/nuodb-helm-charts
[9]: #deploying-nuodb-insights-using-helm-charts
[10]: https://github.com/nuodb/nuodb-helm-charts/blob/master/deploy/nuodb-scc.yaml

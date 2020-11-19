### The instructions on this page are in three parts:

1. **[Getting Started with Helm][4]** covers how to install and configure Helm on a client host. It will walk you through deploying a canary application to make sure Helm is properly configured.
2. **[Deploying NuoDB using Helm Charts][5]** contains a quick primer on the NuoDB domain installation.
2. **[Deploying NuoDB Insights using Helm Charts][9]** covers the installation of NuoDB Insights.


# Getting Started with Helm 

This section will walk you through getting the Helm client installed in your environment. If using Red Hat OpenShift, this page assumes that you already have the OpenShift `oc` client program installed locally and that you are logged into your OpenShift instance.

## Install Helm 3

If you are interested in Helm 2, please follow the [official Helm 2 docs][7].

Every [release][2] of Helm provides binary releases for a variety of OSes. 

1. Download your [desired version][2]
2. Unpack it (`tar -zxvf helm-${helm-version}-linux-amd64.tgz`)

We’ll use Helm version 3.2.4, which can be downloaded via <https://github.com/kubernetes/helm/releases/tag/v3.2.4>.

Run the following commands to install the Helm locally on your Linux client machine:
```bash
$ curl -s https://storage.googleapis.com/kubernetes-helm/helm-3.2.4-linux-amd64.tar.gz | tar xz
$ cd linux-amd64
```

Move the Helm binaries to /usr/local/bin
```
$ mv helm /usr/local/bin
```

If you're running on Mac, we recommend using the Brew Package manager.
```
brew install helm
```

Confirm you can run the Helm client: `helm help`.

## Confirm that the Helm client is installed correctly 

The results should be as follows:

```bash
helm version
version.BuildInfo{Version:"v3.2.4", GitCommit:"0ad800ef43d3b826f31a5ad8dfbb4fe05d143688", GitTreeState:"dirty", GoVersion:"go1.14.3"}
```

# Deploying NuoDB using Helm Charts

The minimal supported version of NuoDB and the NuoDB helm charts is specified in the [Insights Helm Chart Readme](insights/README.md).

For steps to install the NuoDB database please read the documentation in the [NuoDB Helm Charts][8] repository.
At a bare minimum you will need the [Admin Chart](https://github.com/nuodb/nuodb-helm-charts/tree/master/stable/admin) and at least one [Database Chart](https://github.com/nuodb/nuodb-helm-charts/tree/master/stable/database). They have to be installed with `nuocollector.enabled` set to `true`.

# Deploying NuoDB Insights using Helm Charts

The following section outlines the steps in order to deploy NuoDB Insights using this Helm Chart repository.

## Configuration Parameters

The `insights` Helm Chart has a default [`values.yaml`](insights/values.yaml) parameter file that contains configuration parameters specific to that chart.
For configuration options please see the [Insights Helm Chart Readme](insights/README.md).

## Deployment Steps

The order of installation of [`NuoDB Helm Charts`][8] and [`NuoDB Insights`](insights) does not matter.
You can install the components in any order.

### Installing a released version of NuoDB Insights

The default repository for NuoDB is located at https://storage.googleapis.com/nuodb-charts and must be enabled.

To add the charts for your local client, run the `helm repo add` command below:

```
helm repo add nuodb-insights https://storage.googleapis.com/nuodb-insights
"nuodb-insights" has been added to your repositories
```

To list the NuoDB charts added to your repository, run 
```
helm search nuodb
```

You can now install the chart:
```
helm install nuodb-insights/insights [--generate-name | --name releaseName] [--set parameter] [--values myvalues.yaml]
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

You can now install the chart:
```
helm install stable/insights [--generate-name | --name releaseName] [--set parameter] [--values myvalues.yaml]
```

### Installing in different namespace

If NuoDB Insights is installed in the same namespace with NuoDB database, no additional steps are needed.
Otherwise it is required to create NuoDB Collector configuration for Insights in all namespaces where NuoDB admin and database services are running. This can be done by installing the chart and setting `insights.influxdb.host` to the InfluxDB fully qualified domain name. For example:

```bash
helm install nuodb-insights/insights --generate-name -n nuodb \
  --set grafana.enabled=false \
  --set influxdb.enabled=false \
  --set insights.grafana.enabled=false \
  --set influxdb.host=<InfluxDB FQDN> \
  --set insights.nuocollector.enabled=true
```

## Accessing NuoDB Insights

By default Grafana will be available within the Kubernetes cluster via ClusterIP service. One way to access Grafana dashboards is to use port forwarding and navigate to http://localhost:8080/.

```
kubectl port-forward service/<release-name>-grafana 8080:80
```

Grafana 3-rd party chart supports ingress with Grafana 6.3 and above. Configure ingress during NuoDB Insights chart installation and navigate to one of the hosts specified in `grafana.ingress.hosts` variable.
For example:

```
helm install insights nuodb-insights/insights -n nuodb \
  --set grafana.ingress.enabled=true \
  --set grafana.ingress.hosts='{"insights.example.com"}'
```

For OCP deployments the service can be exposed via route.

```
oc expose svc/<release-name>-grafana
```

### Grafana Default Password

By default, Grafana generates a random password when the instance is started.
To retrieve the password, you can read the Kubernetes secret as such:
```
kubectl get secret <release-name>-grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
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

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

## Create the _nuodb_ namespace to install NuoDB

```
kubectl create namespace nuodb
```

You are now ready to install the NuoDB components.

# Deploying NuoDB using Helm Charts

The minimal suppported version of NuoDB and the NuoDB helm charts is specified in the [Insights Helm Chart Readme](insights/README.md).

For steps to install the NuoDB database please read the documentation in the [NuoDB Helm Charts][8] repository.
All components must be installed in the same namespace.
At a bare minimum you will need the [Admin Chart](https://github.com/nuodb/nuodb-helm-charts/stable/admin) and at least one [Database Chart](https://github.com/nuodb/nuodb-helm-charts/stable/database).
The Database chart will have to be started with `global.insights.enabled`.

# Deploying NuoDB Insights using Helm Charts

The following section outlines the steps in order to deploy NuoDB Insights using this Helm Chart repository.

## Configuration Parameters

The `Insights` Helm Chart has a default [`values.yaml`](insights/values.yaml) parameter file that contains configuration parameters specific to that chart.
For configuration options please see the [Insights Helm Chart Readme](insights/README.md).

## Deployment Steps

The order of installation of [`NuoDB Helm Charts`][8] and [`NuoDB Insights`](insights) does not matter.
You can install the components in any order.

### Installing a released version of NuoDB Insights

The default repository for NuoDB is located at https://storage.googleapis.com/nuodb-charts and must be enabled.

To add the charts for your local client, run the `helm repo add` command below:

```
helm repo add nuodb https://storage.googleapis.com/nuodb-charts
"nuodb" has been added to your repositories
```

To list the NuoDB charts added to your repository, run 
```
helm search nuodb/
```

You can now install the chart:
```
helm install nuodb/insights [--generate-name | --name releaseName] [--set parameter] [--values myvalues.yaml]
```


### Installing from source

Clone NuoDB Insights and cd into it:
```
$ git clone git@github.com:nuodb/nuodb-helm-charts.git
$ cd monitoring-influx
```

In order to use this helm chart locally you will need to first update the dependencies:
```
$ helm dep update stable/insights
```

You can now install the chart:
```
helm install stable/insights [--generate-name | --name releaseName] [--set parameter] [--values myvalues.yaml]
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
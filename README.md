<img src="images/nuodb.svg" width="200" height="200" />

# NuoDB Insights - Visual Monitoring

[![Build Status](https://travis-ci.com/nuodb/nuodb-insights.svg?token=nYo6yHzhBM9syBKXYk7y&branch=master)](https://travis-ci.com/nuodb/nuodb-insights)

### Repository Structure:

| Directory | Description                                            |
|-----------|--------------------------------------------------------|
| conf      | dashboards and data sources for provisioning in grafana |
| deploy    | YAML configuration files for the monitor stack |
| images    | contains png included in this README |
| stable    | Helm Charts for Kubernetes Environments |

## Sample Dashboard

<img src="images/InsightsExample.png" alt="Insights Dashboards Example"/>


# NuoDB Insights Page Outline
[Introduction](#Introduction)

[Requirements](#Requirements)

[QuickStart in Docker using Docker Compose](#Quickstart-in-docker-using-docker-compose)

[Setup Manually in Docker using Docker Run](#Setup-manually-in-docker-using-docker-run)

[Setup in Kubernetes](#Setup-in-Kubernetes)

[Setup on Bare Metal Linux](#Setup-on-bare-metal-linux)

[Influx DB migration](#Insights-2.0)

## Introduction

NuoDB Insights is a visual monitor tool that aids NuoDB practitioners in monitoring NuoDB database health, resource consumption, and application workload processed in real-time and historically using an intuitive graphical interface. It can be installed at database startup or after. It also installs locally on the same nodes/hosts your database runs and supports all NuoDB database deployment environments: Kubernetes, Docker, and physical host / Virtual Machine environments. 

## Requirements

| Dependency | Description & version                                 |
|-----------|--------------------------------------------------------|
| [NuoDB](https://nuodb.com/) | A distributed SQL database. 4.0 or newer |
| [NuoDB Collector](https://github.com/nuodb/nuodb-collector)   | The stats collector daemon. 1.1.0 or newer |
| [InfluxDB](https://portal.influxdata.com/downloads/)    | Time-series database. Only version 2.X is supported. NuoDB recommends version 2.7 or later.  |
| [Grafana](https://grafana.com/grafana/download)    | Dashboards visualization. NuoDB recommends version 7.5.4 or later. |

## QuickStart in Docker using Docker Compose

For a complete example on how to set up the NuoDB database with NuoDB Insights monitoring, you can use `docker compose`.
This repository contains a Docker Compose file (`deploy/docker-compose.yml`) which will start:

- 1 Admin Processes
- 1 Storage Manager
- 2 Transaction Engines
- 3 NuoDB Collector containers (1 for SM, 2 for TE)
- 1 InfluxDB database
- 1 Grafana and NuoDB Dashboards
- 1 YCSB Demo Workload generator

Clone the NuoDB Insights repository and `cd` into it:

```
git clone https://github.com/nuodb/nuodb-insights.git
cd nuodb-insights
```

Then run `docker-compose up` to start the processes specified in the Docker Compose file:
```
docker-compose -f deploy/docker-compose.yaml up -d
```

Stop processes started with `docker-compose up` by running the following command:

```
docker-compose -f deploy/docker-compose.yaml down
```

If you already have a NuoDB database running, and you only need to start NuoDB insights, run the `deploy/monitor-stack.yaml` file instead.

Once all components have been installed, NuoDB performance can be visualized by navigating to the NuoDB Insights WebUI dashboard available at http://<hostgrafana>:3000, where `<hostgrafana>` is the host that the Grafana server was started on.
From this login screen, enter the default username and password combination for Grafana which is `admin/admin`.
You will then be prompted to create a new password.
Once logged into the interface, browse the available Dashboards and select the "NuoDB Ops System Overview" to get started!

## Setup manually in Docker using Docker Run

### Download the Docker Images

```
docker pull nuodb/nuodb:latest
docker pull nuodb/nuodb-collector:latest
docker pull influxdb:2.7
docker pull grafana/grafana:9.5.6
```

### Get NuoDB Insights
```
git clone https://github.com/nuodb/nuodb-insights.git
cd nuodb-insights
```

### Starting NuoDB Insights
1. Create a Docker network.

   All NuoDB components should be running on this network.

      
```
docker network create nuodb-net
 ```

2. Start an InfluxDB server.

   Use the provided init script to generate the required databases.
```
docker run -d --name influxdb \
      --network nuodb-net \
      -p 8086:8086 \
      -p 8082:8082 \
      --env DOCKER_INFLUXDB_INIT_MODE=setup \
      --env DOCKER_INFLUXDB_INIT_USERNAME=<your_username> \
      --env DOCKER_INFLUXDB_INIT_PASSWORD=<your_password> \
      --env DOCKER_INFLUXDB_INIT_ORG=<name_of_organization> \
      --env DOCKER_INFLUXDB_INIT_RETENTION=<bucket_retention_time> \
      --env DOCKER_INFLUXDB_INIT_BUCKET=<influxdb_bucket_name> \
      --env DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=<your_influxdb_token> \
      -v $PWD/deploy/initdb.sh:/docker-entrypoint-initdb.d/initdb.sh \
      influxdb:2.7
```
     



3. Start Grafana with the NuoDB dashboards.

```
docker run -d --name grafana \
      --network nuodb-net \
      -p 3000:3000 \
      --env INFLUX_HOST=influxdb \
      --env INFLUXDB_TOKEN=<influxdb_token> \
      -v $PWD/conf/provisioning:/etc/grafana/provisioning \
      grafana/grafana:9.5.6
```

4. If you haven't already, [start your NuoDB database](https://doc.nuodb.com/nuodb/latest/quick-start-guide/docker/).
      
5. Start the [NuoDB Collector](https://github.com/nuodb/nuodb-collector) daemons for each NuoDB database process.      

6. Start the NuoDB YCSB workload generator to explore the various dashboards with live monitoring data.

```
docker run -dit --name ycsb1 \
      --hostname ycsb1 \
      --network nuodb-net \
      --env PEER_ADDRESS=nuoadmin1 \
      --env DB_NAME=test \
      --env DB_USER=dba \
      --env DB_PASSWORD=goalie \
      nuodb/ycsb:latest /driver/startup.sh
```

## Setup in Kubernetes

### Helm Repository Structure

This Github repository contains the NuoDB Insights Helm Chart and all the required components to install and deploy NuoDB Insights.

### Installation

1. **[Getting Started with Helm](stable#getting-started-with-helm)** describes how to install and configure Helm on a client host. 
2. **[Deploying NuoDB using Helm Charts](stable#deploying-nuodb-using-helm-charts)** contains a quick primer on how to deploy a NuoDB database using the NuoDB Helm Charts.
3. **[Deploying NuoDB Insights using Helm Charts](stable#deploying-nuodb-insights-using-helm-charts)** describes how to install and configure NuoDB Insights.

## Setup on Bare Metal Linux

The following installation instructions apply to Red Hat and CentOS Linux distributions on bare-metal or VMs. For other platforms, see [InfluxDB](https://docs.influxdata.com/influxdb/latest/introduction/install/) and [Grafana](https://grafana.com/docs/grafana/latest/installation/) installation instructions.

### 1) Download and install InfluxDB

Install `InfluxDB` on the same host machine referred to by `<hostinflux>` in the [NuoDB Collector](https://github.com/nuodb/nuodb-collector#configuration) installation instructions.

```
wget https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.0.x86_64.rpm
sudo yum localinstall influxdb2-2.7.0.x86_64.rpm
sudo service influxdb start
```

If not using `systemd`, `InfluxDB` can be started directly as follows:

```
env $(cat /etc/default/influxdb | xargs) influxd -config /etc/influxdb/influxdb.conf
```

### 2) Download and install Grafana with NuoDB-Insights dashboards

On a host in your NuoDB domain, install Grafana and configure it to use the NuoDB-Insights dashboards.

```
wget https://dl.grafana.com/oss/release/grafana-9.5.6-1.x86_64.rpm
sudo yum install -y grafana-9.5.6-1.x86_64.rpm

git clone https://github.com/nuodb/nuodb-insights.git
sudo rm -rf /etc/grafana/provisioning
sudo cp -r nuodb-insights/conf/provisioning /etc/grafana
sudo mkdir -p /etc/grafana/provisioning/notifiers /etc/grafana/provisioning/plugins
sudo chown -R root:grafana /etc/grafana/provisioning
sudo chmod 755 $(find /etc/grafana/provisioning -type d)
sudo chmod 640 $(find /etc/grafana/provisioning -type f)
```

Once installed, Grafana can be started with InfluxDB as a datasource by using the `INFLUX_HOST` environment variable. In the below `echo` command, peplace `<hostinflux>` with the machine host name that is running your InfluxDB instance, and run, 

```
echo "INFLUX_HOST=<hostinflux>" >> /etc/sysconfig/grafana-server
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
```

If not using `systemd`, Grafana can be started as follows:

```
sudo /etc/rc.d/init.d/grafana-server start
```

### 3) Install NuoDB Collector on all hosts with database processes

Follow the instructions for installing the [NuoDB Collector on bare-metal](https://github.com/nuodb/nuodb-collector#setup-on-bare-metal). The NuoDB Collector must be set up on all hosts that will run NuoDB database processes.

Once all components have been set up, NuoDB performance can be visualized by navigating to the NuoDB Insights - NuoDB Ops System Overview dashboard at `http://<hostgrafana>:3000/d/000000004/nuodb-ops-system-overview`, where `<hostgrafana>` is the host that the Grafana server was started on. The default password in Grafana is `admin:admin`.

## Insights 2.0

Insights 2.x introduces a breaking change. In this update, a crucial shift is the migration from InfluxDB version 1.8 to 2.7. For those transitioning from the prior Insights 1.x iteration to 2.x, it's important to be aware that access to historical InfluxDB data from the previous version will not be retained due to the migration.

### Migration steps

Run the following command for migrating from Insights 1.2 to 2.0.

```
helm upgrade <release_name>
```

## Status of the Project

This project is still under active development, so you might run into [issues](https://github.com/nuodb/nuodb-insights/issues). If you do, please don't be shy about letting us know, or better yet, contribute a fix or feature.


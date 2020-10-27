# NuoDB Insights - Visual Monitoring

## Introduction

### Repository Structure:

| Directory | Description                                            |
|-----------|--------------------------------------------------------|
| conf      | dashboards and datasources for provisioning in grafana |
| data      | contains an example monitor file to demonstrate batch loading |
| deploy    | yaml configuration files for the monitor stack, nuoca setup and batch job for processing monitor output      |
| images    | contains png included in this README |
| stable    | Helm Charts for Kubernetes Environments |
| systemd   | files to set up nuoca to collect on bare metal |

## Dashboards

### Dashboards Configuration

`conf/provisioning/dashboards/nuodb.yaml` defines the location of the dashboards.

## Quickstart with Docker compose

## Setup manually in Docker

## Setup in Kubernetes

### Helm Repository Structure

This GitHub repository contains the source for the packaged and versioned charts released in the [`gs://nuodb-charts` Google Storage bucket](https://console.cloud.google.com/storage/browser/nuodb-charts/) (the Chart Repository).

This Helm project currently contains only one Helm Chart called `Insights`.
It contains all components required to install NuoDB Insights.
It is located in the [stable](stable/README.md) directory.

This Helm project does not currently contain any `incubator` Charts.

### Installation

If you are new to Kubernetes and Helm please read the [high-level description](stable/README.md) of this Helm repository.

If you are looking for specific configuration options see the [Insights Helm Chart Readme](stable/insights/README.md)

## Setup on Bare Metal

## Status of the Project

This project is still under active development, so you might run into [issues](https://github.com/nuodb/nuodb-insights/issues). If you do, please don't be shy about letting us know, or better yet, contribute a fix or feature.

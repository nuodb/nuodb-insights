# Helm 3 Charts

Charts for deploying dashboards to kubernetes using helm3.

The nuoca chart deploys nuoca collector.  This is a replication set
that will run nuodb container executing the nuoca entrypoint.

The monitoring-influx chart will deploy the dashboards and a
datasource as configmaps.  And contains subcharts for deploying
grafana, influxdb, and nuoca.   The subcharts can be disabled if
existing grafana or influxdb deployments already exist.



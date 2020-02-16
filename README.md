# NuoDB Dashboards - Influx Data Source

This repo contains the set of grafana dashboards for displaying
metrics published by nuoca to the output plugin InfluxDB for input
plugin NuoMon or NuoAdminNuoMon.

The dashboqrds are located in the conf sub directory.

In addition, to the dashboards there exist configurations for starting
the stack of influxdb , grafana, and nuoca as a set of docker
containers with `docker stack` to kubernetes.  There is also a docker
build for nuomonitor:1.0 image which can be used to parse `nuodbmgr
monitor domain` and run that as a job in the kubernetes environment
that is running the stack.

### Content:

| Directory | Description                                            |
|-----------|--------------------------------------------------------|
| conf      | dashboards and datasources for provisioning in grafana |
| data      | contains an example monitor file to demonstrate batch loading |
| deploy    | yaml configuration files for the monitor stack, nuoca setup and batch job for processing monitor output      |
| doc       | contains images included in this README |
| image     | docker build to build batch image |



## Dashboards

The grafana dashboards and datasources are configured to be dropped in as provisioned data sources and dashboards in grafana rpm install.   With the RPM install the location of the provisioning directory is /etc/grafana/provisioning.  In /etc/grafana/provisioning/nuodb.yaml `(conf/provisioning/dashboards/nuodb.yaml)` there is a hardcoded path:

```
options:
    path: /etc/grafana/provisioning/dashboards
```

Which is location of the dashboard json files.  If the dashboards are installed in a tarball install.  Then this hardcoded path should be changed to config/provisioning/dashboards.  See [grafana documentation on Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)

This points to the location of the provisioning directory which is where the dashboard json files are located.   In a tarball install this directory will be different and can be specified relative to the tarball directory.

```
options:
    path: config/provisioning/dashboards
```

## Running Dashboards

To run the stack of grafana, influxdb, and nuoca you can use `docker stack`.

With _docker for desktop_ configure your docker stack to run in kubernetes.

![Configure stack to use kubernetes](doc/docker-for-desktop.png)


You'll need to make some modifications to the files in deploy for your environment.

* **deploy/monitor-stack.yaml** - if you are not running the dashboards live then comment out the `nuoca` section.  if you are running the dashboards live then set the `volumes` to either the nuoca.yml.nuoadmin or nuoca.yml.nuoagent depending upon which version of admin is managing your domain.

  - not using nuoca
  
  ```yaml
  version: '3'
  services:
    influxdb:
      ...
    grafana:
      ...
  #  nuoca:
  #    image: nuodb/nuodb-ce:latest
  #    labels:
  #      - "owner=${USER}"
  #    command: [ "nuoca", "start" , "nuoca", "--collection-interval", "10", "--config-template", "/tmp/nuoca.yml.template" ]
  #    volumes:
  #      - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
  ##      - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```

  - using nuoca with nuoadmin

  ```yaml
  version: '3'
  services:
    influxdb:
      ...
    grafana:
      ...
    nuoca:
      ...
      volumes:
        - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
  #      - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```

  - using nuoca with nuoagent

  ```yaml
  version: '3'
  services:
    influxdb:
      ...
    grafana:
      ...
    nuoca:
      ...
      volumes:
  #       - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
        - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```



* **deploy/nuoca.yml.nuoadmin** - you'll want to change the api-server settings.  This file is setup to run with a domain not using ssl.   If you are using ssl you might need to add additional options for the nuoadmin certificate.  Likewise,  you are likely going to have to change the moitor-stack.yaml to mount the certificate.

* **deploy/nuoca.yml.nuoagent** - you'll wnat to change the settings in `NuoMon`. See nuoca documentation.

Once configuration files are correct you can deploy the stack in kubernetes with.

`docker stack deploy monitor -c deploy/monitor-stack.yaml`

To undeploy

`docker stack rm monitor`

Any data loaded is persisted in the directory lib/influxdb.  On restart the data should still be available.  remove lib/influxdb to reset the influx database.

## Loading Monitor Files 

To load a monitor file into Influx,  you will need to modify the
_deploy/load.yaml_ file.  Three changes to make.

* 2 volumes.hostPath.path
  - modify `/Users/dbutson/home/dev/nuodb-dashboards-influx`
* containers.args
  - modify last argument `/data/monitor-20200108-034803.log`.
* Place your monitor file in the data directory.


```yaml
    apiVersion: batch/v1
    kind: Job
    metadata:
      name: load
    spec:
      template:
        spec:
          containers:
            - name: load
              image: nuodb/nuodb-ce:latest
              args: [ "batch",  "-H", "influxdb", "/data/monitor-20200108-034803.log" ]
              ...
          ...
          volumes:
          - name: mount-0
            hostPath:
              path: /Users/dbutson/home/dev/nuodb-dashboards-influx/data
              type: ""
          - name: mount-1
            hostPath:
              path: /Users/dbutson/home/dev/nuodb-dashboards-influx/image
              type: ""
```
The monitor file can be in compressed format (e.g. *monitor.log.gz*). 

To run the batch job:

```
$ kubectl create -f deploy/load.yaml
```

To remove deployment:

```
$ kubectl delete -f deploy/load.yaml
```

# NuoDB Dashboards - Influx Data Source

This repo contains the set of grafana dashboards for displaying
metrics published by nuoca to the output plugin InfluxDB for input
plugin NuoMon or NuoAdminNuoMon.

The dashboards are located in the conf sub directory.

A *docker stack* can be created with grafana, insights, and nuoca with
the compose file **deploy/monitor-stack.yaml**.  nuoca can be
configured to point to either an existing nuoadmin or nuoagent
domain.  Or comment out, nuoca and deploy a batch.job to load an
existing `nuodbmgr monitor database` output file.  The output file can
be optionally be compressed.  An example exists in the data directory.

### Content:

| Directory | Description                                            |
|-----------|--------------------------------------------------------|
| conf      | dashboards and datasources for provisioning in grafana |
| data      | contains an example monitor file to demonstrate batch loading |
| deploy    | yaml configuration files for the monitor stack, nuoca setup and batch job for processing monitor output      |
| doc       | contains png included in this README |
| image     | scripts for batch processing, these are mounted into batch.job |


## Dashboards

The grafana dashboards and datasources are configured as used in the
docker stack in this repo.  This docker stack is created with the
basic installation of grafana.   If the dashboards are used in another
grafana installation some changes will need to be made to:

* **conf/provisioning/dashboards/nuodb.yaml**
* **conf/provisioning/datasources/nuodb.yaml**

For an explanation of these data files, see the grafana documentation
at
[grafana documentation on Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/).

### Dashboards Configuration

`conf/provisioning/dashboards/nuodb.yaml` defines the location of the
dashboards.  I've chosen to store the dashboards in the same location
as the configuration file.  This is
*/etc/grafana/provisioning/dashboards* in the grafana docker container
or any default RPM install.

## Running Monitor Stack

To run the stack of grafana, influxdb, and nuoca you can use `docker stack`.

With _docker for desktop_ configure your docker stack to run in kubernetes.

![Configure stack to use kubernetes](doc/docker-for-desktop.png)

You'll need to make some modifications to the compose file
**deploy/monitor-stack.yaml** that is used to define the monitor stack
and specifically the `nuoca:` section. 

  - not using nuoca

  ```yaml
  version: '3'
  services:
    ...

  #   nuoca:
  #      image: nuodb/nuodb-ce:latestn
  #      labels:
  #      - "owner=${USER}"
  #      environment:
  #      - NUODB_API_SERVER=http://nuoadmin.local:8888
  #      - NUODB_INSIGHTS_KEY=/etc/nuodb/keys/nuocmd.pem
  #      - DOMAIN_USER=domain
  #      - DOMAIN_PASSWORD=bird
  #      - DOMAIN_BROKER=nuoagent.local
  #      command: [ "nuoca", "start" , "nuoca", "--collection-interval", "10", "--config-template", "/tmp/nuoca.yml.template" ]
  #      volumes:
  #        - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
  ##        - ../deploy/nuocmd.pem:/etc/nuodb/keys/nuocmd.pem
  ##        - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```

  - using nuoca with nuoadmin without ssl

  ```yaml
  version: '3'
  services:
    ...

     nuoca:
        image: nuodb/nuodb-ce:latestn
        labels:
        - "owner=${USER}"
        environment:
        # change NUODB_API_SERVER
        - NUODB_API_SERVER=http://nuoadmin.local:8888 
        - NUODB_INSIGHTS_KEY=/etc/nuodb/keys/nuocmd.pem
        - DOMAIN_USER=domain
        - DOMAIN_PASSWORD=bird
        - DOMAIN_BROKER=nuoagent.local
        command: [ "nuoca", "start" , "nuoca", "--collection-interval", "10", "--config-template", "/tmp/nuoca.yml.template" ]
        volumes:
          - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
  #        - ../deploy/nuocmd.pem:/etc/nuodb/keys/nuocmd.pem
  #        - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```

  - using nuoca with nuoadmin with ssl

  ```yaml
  version: '3'
  services:
    ...

     nuoca:
        image: nuodb/nuodb-ce:latestn
        labels:
        - "owner=${USER}"
        environment:
        # change NUODB_API_SERVER
        - NUODB_API_SERVER=https://nuoadmin.local:8888 
        - NUODB_INSIGHTS_KEY=/etc/nuodb/keys/nuocmd.pem
        - DOMAIN_USER=domain
        - DOMAIN_PASSWORD=bird
        - DOMAIN_BROKER=nuoagent.local
        command: [ "nuoca", "start" , "nuoca", "--collection-interval", "10", "--config-template", "/tmp/nuoca.yml.template" ]
        volumes:
          - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
          - ../deploy/nuocmd.pem:/etc/nuodb/keys/nuocmd.pem
  #        - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```

  
  - using nuoca with nuoagent


  ```yaml
  version: '3'
  services:
    ...

     nuoca:
        image: nuodb/nuodb-ce:latestn
        labels:
        - "owner=${USER}"
        environment:
        - NUODB_API_SERVER=http://nuoadmin.local:8888 
        - NUODB_INSIGHTS_KEY=/etc/nuodb/keys/nuocmd.pem
        # change DOMAIN_USER, DOMAIN_PASSWORD, DOMAIN_BROKER
        - DOMAIN_USER=domain
        - DOMAIN_PASSWORD=bird
        - DOMAIN_BROKER=nuoagent.local
        command: [ "nuoca", "start" , "nuoca", "--collection-interval", "10", "--config-template", "/tmp/nuoca.yml.template" ]
        volumes:
  #        - ../deploy/nuoca.yml.nuoadmin:/tmp/nuoca.yml.template
  #        - ../deploy/nuocmd.pem:/etc/nuodb/keys/nuocmd.pem
          - ../deploy/nuoca.yml.nuoagent:/tmp/nuoca.yml.template
  ```

Once the compose files are correct you can deploy the stack in your local
kubernetes cluster with:

`docker stack deploy monitor -c deploy/monitor-stack.yaml`

If you are not _using docker for desktop_ you can try and start the stack with `docker compose`.

```
docker-compose -p ${USER} -f deploy/monitor-stack.yaml up > ${USER}-stack.yaml &
```

To undeploy with `docker stack`

```
docker stack rm monitor
```

Note, if you use *kubectl* to delete the deployments docker stacks
will reinstall.

To undeploy with `docker-compose`

```
docker-compose -p ${USER} -f deploy/monitor-stack.yaml down
```

Any data loaded is persisted in the directory lib/influxdb.  On
restart the data should still be available.  remove lib/influxdb to
reset the influx database.

## Loading Monitor Files 

To load a monitor file into Influx,  you will need to modify the
_deploy/load.yaml_ file if you are using `docker stack` mapped to
local kubernetes.

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
        args: [ "batch",  "-H", "influxdb", "/data/monitor-20200107-034803.log.gz" ]
        volumeMounts:
        - mountPath: /data
          name: mount-0
        - mountPath: /opt/nuodb/etc/nuoca/lib/batch.py
          name: mount-1
          subPath: batch.py
        - mountPath: /usr/local/bin/batch
          name: mount-1
          subPath: batch
      restartPolicy: Never
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

You will need to modify `args:` to your monitor filename, and the
`hostPath.path:` to the absolute path of the data and image
directories.  Put your monitor file in the data directory.

If you are using docker-compose then make modifications to the docker
compose file `deploy/load-compose.yaml`.  Unfortunately,  I've been
unable to use `docker stack` to fire a batch.job. Thus, the need for
two different load files.

```
version: '3'
services:
  load:
    image: nuodb/nuodb-ce:latest
    labels:
      - "owner=${USER}"
    command: [ "batch",  "-H", "influxdb", "/data/monitor-20200107-034803.log.gz" ]
    volumes:
      - ../data:/data
      - ../image/batch.py:/opt/nuodb/etc/nuoca/lib/batch.py
      - ../image/batch:/usr/local/bin/batch
networks:
  default:
    driver: bridge
```

You will modify the `command:` to reference your monitor file.  You
might need to change version from 3 to 2 if you are running an older
version of docker or docker-compose.

To run the batch job with `docker stack` deployment.

```
$ kubectl create -f deploy/load.yaml
```

To run the batch job with `docker-compose` deployment.

```
$ docker-compose -p ${USER} -f deploy/load-compose.yaml up
```

The -p option is important to get the same network.  You'll see warns
such as below that you can ignore.

```
nuodb-dashboards-influx git:(master) ✗ docker-compose -p dbutson -f deploy/load-compose.yaml up

WARNING: Found orphan containers (dbutson_grafana_1, dbutson_nuoca_1, dbutson_influxdb_1) for this project. If you removed or renamed this service in your compose file, you can run this command with the --remove-orphans flag to clean it up.
Creating dbutson_load_1 ... done
Attaching to dbutson_load_1
```


To remove the `docker stack` deployment

```
$ kubectl delete -f deploy/load.yaml
```

To remote the `docker-compose` deployment

```
$ docker-compose -p ${USER} -f deploy/load-compose.yaml down
```


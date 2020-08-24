FROM python:2.7.18-slim-stretch

COPY  --chown=1000:0 nuocd /opt/nuocd
WORKDIR /opt/nuocd
COPY --chown=1000:0 requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get update -y && \
    apt-get install -y gettext-base apt-transport-https curl gnupg procps && \
    curl -sL https://repos.influxdata.com/influxdb.key | apt-key add - && \
    echo "deb https://repos.influxdata.com/debian stretch stable" > /etc/apt/sources.list.d/influxdb.list && \
    apt-get update -y && \
    useradd -d /opt/nuocd -g 0 -u 1000 -s /bin/false telegraf && \
    apt-get -y install telegraf && \
    apt-get clean


RUN chmod g+w /etc
COPY --chown=telegraf:0 conf/telegraf.conf  /etc/telegraf/telegraf.conf
COPY --chown=telegraf:0 conf/nuodb.conf     /etc/telegraf/telegraf.d/nuodb.conf
COPY --chown=telegraf:0 conf/outputs.conf   /etc/telegraf/telegraf.d/outputs.conf


USER 1000:0

CMD ["telegraf", "--config", "/etc/telegraf/telegraf.conf", "--config-directory", "/etc/telegraf/telegraf.d"]
#CMD ["/opt/nuocd/docker-entrypoint.sh"]


#!/bin/bash

cat > /etc/telegraf/telegraf.d/bootstrap.conf <<EOF
[[outputs.file]]
  files = ["stdout"]
  data_format = "json"
EOF
chmod 666 /etc/telegraf/telegraf.d/bootstrap.conf

telegraf --config /etc/telegraf/telegraf.conf --config-directory /etc/telegraf/telegraf.d

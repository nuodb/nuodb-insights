#!/bin/sh
set -e

influx bucket create --name nuodb_internal --retention 365d --shard-group-duration 1d

influx bucket create --name nuodb --retention 365d --shard-group-duration 1d

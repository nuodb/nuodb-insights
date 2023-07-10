#!/bin/sh
set -e

influx bucket create --name nuodb_internal --retention 365d

influx bucket create --name nuodb --retention 365d

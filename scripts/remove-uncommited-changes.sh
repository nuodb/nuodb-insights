#!/bin/sh

set -e

#change to root directory
cd "$(dirname "$0")/.."
git checkout -f -- "./stable/insights/Chart.lock"

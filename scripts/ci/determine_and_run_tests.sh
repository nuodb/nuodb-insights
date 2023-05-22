#!/usr/bin/env bash

echo "Running $TEST_SUITE"

if [[ $TEST_SUITE = "Kubernetes"  ]]; then
  gotestsum --junitfile /tmp/test-results/gotestsum-report-${CIRCLE_BUILD_NUM}.xml --format testname -- ./test/minikube
  # go test -timeout 50m -v ./test/minikube
elif [[ $TEST_SUITE = "docker"  ]]; then
  gotestsum --junitfile /tmp/test-results/gotestsum-report-${CIRCLE_BUILD_NUM}.xml --format testname -- ./test/docker
  # go test -timeout 50m -v ./test/docker
fi
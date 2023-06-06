#!/usr/bin/env bash

echo "Running $TEST_SUITE"

if [[ $TEST_SUITE = "Kubernetes"  ]]; then
  gotestsum --junitfile ${TEST_RESULTS}/gotestsum-report-${CIRCLE_BUILD_NUM}.xml --format testname -- ./test/minikube
elif [[ $TEST_SUITE = "docker"  ]]; then
  gotestsum --junitfile ${TEST_RESULTS}/gotestsum-report-${CIRCLE_BUILD_NUM}.xml --format testname -- ./test/docker
fi
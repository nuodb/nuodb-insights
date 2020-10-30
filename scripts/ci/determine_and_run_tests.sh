#!/usr/bin/env bash

echo "Running $TEST_SUITE"

if [[ $TEST_SUITE = "Kubernetes"  ]]; then
  go test -timeout 50m -v ./test/minikube
elif [[ $TEST_SUITE = "docker"  ]]; then
  go test -timeout 50m -v ./test/docker
fi
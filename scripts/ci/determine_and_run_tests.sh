#!/usr/bin/env bash

echo "Running $TEST_SUITE"

if [[ $TEST_SUITE = "minikube"  ]]; then
  go test -timeout 50m -v ./test/minikube
if [[ $TEST_SUITE = "docker"  ]]; then
  go test -timeout 50m -v ./test/docker
fi
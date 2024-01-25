#!/usr/bin/env bash

# exit when any command fails
set -ex

curl -sSL https://github.com/gotestyourself/gotestsum/releases/download/v"${GOTESTSUM_VERSION}"/gotestsum_"${GOTESTSUM_VERSION}"_linux_amd64.tar.gz | sudo tar -xz -C /usr/local/bin gotestsum

if [[ $TEST_SUITE = "Kubernetes"  ]]; then

  # Download kubectl, which is a requirement for using minikube.
  curl -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/v"${KUBERNETES_VERSION}"/bin/linux/amd64/kubectl && chmod +x kubectl && sudo mv kubectl /usr/local/bin/

  sudo apt-get update

  # Make test dir to store test results
  mkdir -p "${TEST_RESULTS}"

  # conntrack is required by Minikube
  sudo apt-get install -y conntrack

  wget https://get.helm.sh/helm-"${HELM_VERSION}"-linux-amd64.tar.gz -O /tmp/helm.tar.gz
  tar xzf /tmp/helm.tar.gz -C /tmp --strip-components=1 && chmod +x /tmp/helm && sudo mv /tmp/helm /usr/local/bin

  # Download minikube.
  curl -Lo minikube https://storage.googleapis.com/minikube/releases/v"${MINIKUBE_VERSION}"/minikube-linux-amd64 && chmod +x minikube && sudo mv minikube /usr/local/bin/

  # start minikube
  minikube start --vm-driver=docker --kubernetes-version=v"${KUBERNETES_VERSION}" --cpus=max --memory=max
  minikube status
  kubectl cluster-info
  cat <<EOF > valuesInject.yaml
database:
  te:
    resources:
      limits:
        cpu: 2
        memory: 2Gi
  sm:
    resources:
      limits:
        cpu: 2
        memory: 2Gi
EOF

  helm version

  kubectl version

  echo "Downloading dependencies"
  helm dep update stable/insights

  # Use NuoDB helm charts for integration testing
  if [[ $NUODB_HELM_CHARTS_VERSION =~ ^([0-9]+\.?){1,3}$ ]]; then
    # Use already released chart versions
    echo "Testing with NuoDB Helm Charts v${NUODB_HELM_CHARTS_VERSION}"
    helm repo add nuodb https://nuodb.github.io/nuodb-helm-charts
    helm repo add nuodb-incubator https://nuodb.github.io/nuodb-helm-charts/incubator
  else
    git clone https://github.com/nuodb/nuodb-helm-charts ../nuodb-helm-charts
    pushd ../nuodb-helm-charts
    if [ -n "$NUODB_HELM_CHARTS_VERSION" ]; then
      # Checkout revision/branch/tag if specified; otherwise use latest master
      git checkout "${NUODB_HELM_CHARTS_VERSION}"
    fi
    echo -e "--- Checked out nuodb-helm-charts branch $(git rev-parse --abbrev-ref HEAD):\n\n$(git log -n1 HEAD)"
    popd
    # Create symbolic links so that `testlib` can install local charts
    ln -s ${PWD}/../nuodb-helm-charts/stable/admin stable/admin
    ln -s ${PWD}/../nuodb-helm-charts/stable/database stable/database
    mkdir incubator
    ln -s ${PWD}/../nuodb-helm-charts/incubator/demo-ycsb incubator/demo-ycsb
  fi

elif [[ $TEST_SUITE = "docker"  ]]; then
  mkdir -p "${TEST_RESULTS}"
  docker version
  docker-compose version
else
  echo "Skipping installation steps"
fi

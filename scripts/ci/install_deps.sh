#!/usr/bin/env bash

# exit when any command fails
set -e

# Download kubectl, which is a requirement for using minikube.
curl -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/v"${KUBERNETES_VERSION}"/bin/linux/amd64/kubectl && chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Download Helm and Tiller
wget https://get.helm.sh/helm-"${HELM_VERSION}"-linux-amd64.tar.gz -O /tmp/helm.tar.gz
tar xzf /tmp/helm.tar.gz -C /tmp --strip-components=1 && chmod +x /tmp/helm && sudo mv /tmp/helm /usr/local/bin

if [[ -n "$REQUIRES_MINIKUBE" ]]; then
    # Download minikube.
  curl -Lo minikube https://storage.googleapis.com/minikube/releases/v"${MINIKUBE_VERSION}"/minikube-linux-amd64 && chmod +x minikube && sudo mv minikube /usr/local/bin/
  mkdir -p "$HOME"/.kube "$HOME"/.minikube
  touch "$KUBECONFIG"

  # start minikube
  sudo minikube start --vm-driver=none --kubernetes-version=v"${KUBERNETES_VERSION}" --memory=8000 --cpus=4
  sudo chown -R travis: /home/travis/.minikube/
  kubectl cluster-info

  # In some tests (specifically TestKubernetesTLSRotation), we observe incorrect DNS resolution 
  # after pods have been re-created which causes problems with inter pod communicataion.
  # Set CoreDNS TTL to 0 so that DNS entries are not cached. 
  kubectl get cm coredns -n kube-system -o yaml | sed -e 's/ttl [0-9]*$/ttl 0/' | kubectl apply -n kube-system -f -
  kubectl delete pods -l k8s-app=kube-dns -n kube-system

  helm version

  kubectl version
else
  echo "Skipping installation steps"
fi

echo "Downloading dependencies"
helm dep update stable/insights
#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Local end-to-end setup for the Wisecow assessment on a Kind cluster.
# Brings up: Kind cluster -> ingress-nginx -> cert-manager -> KubeArmor
# then deploys Wisecow with TLS and applies the zero-trust policies.
#
# Prereqs on your machine: docker, kind, kubectl, helm (for KubeArmor).
# Run from the repo root:  ./scripts/setup-local.sh
# -----------------------------------------------------------------------------
set -euo pipefail

CLUSTER=${CLUSTER:-wisecow}
IMAGE=${IMAGE:-ghcr.io/OWNER/wisecow:latest}

echo "==> 1. Create Kind cluster (with ingress-ready port mappings)"
cat <<'EOF' | kind create cluster --name "${CLUSTER}" --config=- || true
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
EOF

echo "==> 2. Install ingress-nginx"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=180s

echo "==> 3. Install cert-manager"
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=180s

echo "==> 4. Install KubeArmor (via helm)"
helm repo add kubearmor https://kubearmor.github.io/charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install kubearmor-operator kubearmor/kubearmor-operator \
  -n kubearmor --create-namespace
kubectl apply -f https://raw.githubusercontent.com/kubearmor/KubeArmor/main/pkg/KubeArmorOperator/config/samples/sample-config.yaml || true
echo "    (give KubeArmor ~60s to initialise its daemonset)"
sleep 30

echo "==> 5. (If using a local image) load it into Kind"
echo "    docker build -t ${IMAGE} . && kind load docker-image ${IMAGE} --name ${CLUSTER}"

echo "==> 6. Deploy Wisecow + TLS"
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-deployment.yaml
kubectl apply -f k8s/02-service.yaml
kubectl apply -f k8s/03-tls-issuer.yaml
kubectl apply -f k8s/04-ingress-tls.yaml
kubectl -n wisecow rollout status deploy/wisecow --timeout=120s || true

echo "==> 7. Apply zero-trust KubeArmor policies"
kubectl apply -f kubearmor/zero-trust-allow.yaml
kubectl apply -f kubearmor/zero-trust-block.yaml

cat <<'EOF'

==> Done.
   Add to /etc/hosts:    127.0.0.1  wisecow.local
   Test TLS:             curl -kv https://wisecow.local/
   Watch violations:     karmor logs -n wisecow   (install: curl -sfL https://raw.githubusercontent.com/kubearmor/kubearmor-client/main/install.sh | sudo sh -s -- -b /usr/local/bin)
   Trigger a violation:  kubectl -n wisecow exec -it deploy/wisecow -- cat /etc/shadow
EOF

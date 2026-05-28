# Wisecow — AccuKnox DevOps Trainee Practical Assessment

End-to-end solution covering all three problem statements:

1. **PS1** — Containerise & deploy Wisecow on Kubernetes with CI/CD and TLS.
2. **PS2** — Two automation scripts (System Health Monitor + App Health Checker).
3. **PS3** — Zero-trust KubeArmor policy with captured violations.

The upstream app (`wisecow.sh`) is a Bash HTTP server that pipes `fortune`
through `cowsay` and serves it over `netcat` on port **4499**.

---

## Repository layout

```
.
├── Dockerfile                       # PS1: container image
├── wisecow.sh                       # upstream application
├── k8s/                             # PS1: Kubernetes manifests
│   ├── 00-namespace.yaml
│   ├── 01-deployment.yaml
│   ├── 02-service.yaml
│   ├── 03-tls-issuer.yaml           # cert-manager self-signed CA chain
│   └── 04-ingress-tls.yaml          # TLS-terminating Ingress
├── .github/workflows/ci-cd.yaml     # PS1: build → push (GHCR) → deploy
├── scripts/
│   ├── system_health_monitor.py     # PS2 #1
│   ├── app_health_checker.py        # PS2 #4
│   └── setup-local.sh               # one-shot Kind bring-up
└── kubearmor/                       # PS3: zero-trust policies
    ├── zero-trust-allow.yaml        # whitelist (least-permissive)
    ├── zero-trust-block.yaml        # explicit high-signal blocks
    └── violation-screenshot.png     # <-- add your captured screenshot here
```

---

## PS1 — Containerisation & Kubernetes deployment

### Build & run locally
```bash
docker build -t ghcr.io/<owner>/wisecow:latest .
docker run --rm -p 4499:4499 ghcr.io/<owner>/wisecow:latest
curl http://localhost:4499        # ASCII cow with wisdom
```

### Deploy to a local cluster (Kind)
```bash
./scripts/setup-local.sh          # cluster + ingress + cert-manager + KubeArmor + app
echo "127.0.0.1 wisecow.local" | sudo tee -a /etc/hosts
curl -kv https://wisecow.local/   # TLS-secured access
```

The Wisecow app is exposed as a **ClusterIP Service** (`k8s/02-service.yaml`)
on port 80 → targetPort 4499, and externally via the **Ingress** with TLS.

### TLS implementation
TLS is handled by **cert-manager** issuing a certificate from a self-signed CA
(`03-tls-issuer.yaml`) into the `wisecow-tls` secret, which the NGINX Ingress
(`04-ingress-tls.yaml`) uses to terminate HTTPS for host `wisecow.local`.
`ssl-redirect` forces HTTP → HTTPS. For a public cluster, swap the self-signed
`ClusterIssuer` for a Let's Encrypt ACME issuer — the Ingress stays the same.

---

## CI/CD — GitHub Actions (`.github/workflows/ci-cd.yaml`)

- **build-and-push**: on every push/tag, builds the image with Buildx and
  pushes to **GHCR** (`ghcr.io/<owner>/wisecow`) tagged with branch, semver,
  `sha-<commit>`, and `latest`. Uses the built-in `GITHUB_TOKEN` (no secrets to
  manage for the registry).
- **deploy** *(Challenge goal)*: on push to `main`, applies the manifests and
  rolls the Deployment to the new immutable `sha-` tag, then waits for rollout.

### Required repo settings / secrets
- Enable **Read and write permissions** for Actions (Settings → Actions →
  General → Workflow permissions) so it can push to GHCR.
- Add secret **`KUBE_CONFIG_DATA`** = base64 of a kubeconfig that can reach your
  cluster, for the `deploy` job:
  ```bash
  base64 -w0 ~/.kube/config
  ```
  (For a private Kind cluster, use a self-hosted runner instead.)

---

## PS2 — Automation scripts (chose objectives #1 and #4)

Both are pure standard-library Python 3, log to console **and** a file.

### 1. System Health Monitor — `scripts/system_health_monitor.py`
Checks CPU, memory, disk and top processes; alerts when a threshold is crossed.
```bash
python3 scripts/system_health_monitor.py                 # one-shot
python3 scripts/system_health_monitor.py --watch 10      # every 10s
python3 scripts/system_health_monitor.py --cpu 70 --mem 75 --disk 85
```
Sample alert:
```
WARNING  ALERT - HIGH CPU - CPU usage: 91.2%  (threshold 80%)
```

### 4. Application Health Checker — `scripts/app_health_checker.py`
Reports **UP/DOWN** per URL based on HTTP status (2xx/3xx = up by default).
```bash
python3 scripts/app_health_checker.py https://example.com
python3 scripts/app_health_checker.py --file urls.txt --watch 30
python3 scripts/app_health_checker.py https://wisecow.local --insecure --ok 200
```
Sample output:
```
INFO     UP   | https://github.com | HTTP 200 OK | 71ms
WARNING  ALERT - DOWN | https://api.example.com | HTTP 503 Service Unavailable | 120ms
```
Exits non-zero if any target is down (handy for cron/monitoring).

---

## PS3 — Zero-trust KubeArmor policy

`kubearmor/zero-trust-allow.yaml` puts the Wisecow pods into **whitelist mode**:
once an `Allow` policy exists, everything not explicitly allowed is denied
(default posture `block`). The allow-list contains exactly what `wisecow.sh`
needs — `bash`, `nc`, `cowsay`/`perl`, `fortune`, the coreutils it calls, the
files/libs they read, and `tcp`/`udp` networking only.

`kubearmor/zero-trust-block.yaml` adds explicit, high-signal `Block` rules
(credential file reads, writes to system bin dirs, package-manager/priv-tool
execution) for clear violation telemetry.

### Apply & verify
```bash
kubectl apply -f kubearmor/zero-trust-allow.yaml
kubectl apply -f kubearmor/zero-trust-block.yaml

# Install karmor CLI and stream alerts
curl -sfL https://raw.githubusercontent.com/kubearmor/kubearmor-client/main/install.sh | sudo sh -s -- -b /usr/local/bin
karmor logs -n wisecow
```

### Trigger violations (for the screenshot)
```bash
# 1. Blocked credential read
kubectl -n wisecow exec -it deploy/wisecow -- cat /etc/shadow
# 2. Blocked package manager (not in whitelist + explicit block)
kubectl -n wisecow exec -it deploy/wisecow -- apt-get update
# 3. Blocked arbitrary binary (whitelist denial)
kubectl -n wisecow exec -it deploy/wisecow -- ls /
```
Each produces a `Permission denied` in the pod and a `Block`/violation event in
`karmor logs`. **Capture that output and save it as
`kubearmor/violation-screenshot.png`.**

---

## Notes
- Replace `OWNER` / `<owner>` with your GitHub username/org in
  `k8s/01-deployment.yaml` and commands above.
- Repo should be **public** per the assessment.

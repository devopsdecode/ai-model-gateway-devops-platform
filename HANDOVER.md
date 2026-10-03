# Handover Document

Date: 2026-10-03
Project: AI Model Gateway / 3-Tier Enterprise AI Platform

## 1. Current status

The Azure AKS environment, ACR, and self-hosted GitHub runner are configured and validated for deployment.

- Azure subscription: `Azure subscription 1`
- Subscription ID: `cd459aae-8e9d-4069-8ab8-fd60d11b3e04`
- Resource group: `master-node-rg-fresh`
- AKS cluster: `aks-end-to-end-project`
- ACR: `endtoendproject.azurecr.io`
- Kubernetes namespace: `production`
- Self-hosted runner VM: `20.235.19.182`
- Runner OS user: `azureuser`

The active Azure identity used from the laptop has Owner access at the subscription level and on the VM resource scope. This was confirmed with `az role assignment list` and `az account show`.

## 2. What was fixed

### Azure and AKS access
- Verified Azure login and subscription context.
- Verified AKS cluster exists and is reachable.
- Verified `az aks get-credentials` succeeds for the cluster.
- Verified cluster node readiness with `kubectl get nodes`.

### Self-hosted runner
- The runner user `azureuser` was fixed to access Docker.
- The Docker group was corrected with:
  ```bash
  sudo usermod -aG docker azureuser
  sudo systemctl restart docker
  ```
- Docker access was validated with `docker ps` as `azureuser`.
- Azure CLI was validated with `az account show` and `az aks get-credentials` as `azureuser`.

### GitHub Actions workflow
- The pipeline in [.github/workflows/ci-cd-pipeline.yml](.github/workflows/ci-cd-pipeline.yml) was aligned to the live Azure values.
- The ACR login step was corrected to avoid the `jq` dependency and the wrong token field issue.
- The workflow now obtains the ACR refresh token correctly and passes it to Docker with `--password-stdin`.

### Backend test issue
- The backend test import issue was resolved by making the module import path explicit and using correct async fixture setup.
- Local validation showed backend tests passed successfully.

## 3. Deployment architecture

Repository components:
- Backend: `BE/`
- Frontend: `FE/`
- Kubernetes manifests: `runner-node-master-node/k8s/`
- Helm chart: `runner-node-master-node/helm/ai-app-chart/`

Deployment flow:
1. GitHub Actions runs tests and security checks.
2. Self-hosted runner builds backend and frontend images.
3. Images are pushed to ACR.
4. Runner authenticates to AKS.
5. Helm deploys the stack into `production` namespace.

## 4. Important files

- Pipeline: [.github/workflows/ci-cd-pipeline.yml](.github/workflows/ci-cd-pipeline.yml)
- Ingress: [runner-node-master-node/k8s/05-ingress.yaml](runner-node-master-node/k8s/05-ingress.yaml)
- Helm chart: [runner-node-master-node/helm/ai-app-chart](runner-node-master-node/helm/ai-app-chart)
- Backend app: [BE/app](BE/app)
- Frontend app: [FE/src](FE/src)

## 5. Verified commands

These commands were validated in the environment:

```bash
az account show
az aks get-credentials --resource-group master-node-rg-fresh --name aks-end-to-end-project --overwrite-existing
kubectl get nodes
kubectl config current-context
az role assignment list --assignee <user> --all --output table
```

Observed cluster state:
```text
NAME                                            STATUS   ROLES   AGE   VERSION
aks-agentpool-40722125-vmss000000   Ready    <none>  ...   v1.35.7
```

## 6. Known risk / remaining items

- The self-hosted runner VM must keep Docker access for `azureuser` after any VM restart.
- If the runner service was installed under a different user, it must be restarted under `azureuser`.
- Any future workflow run must trigger on the `main` branch or via `workflow_dispatch`.
- Ensure the runner remains allowed to reach the Azure subscription and resource group used by AKS and ACR.

## 7. Recommended next actions

1. Push the latest workflow changes to GitHub.
2. Trigger the pipeline again from GitHub Actions.
3. Confirm the `build-and-push` job completes without Docker socket permission errors.
4. Confirm the `deploy-to-aks` step successfully installs or upgrades the Helm chart.
5. Verify the public ingress endpoint resolves and application routes work.

## 8. Short operational notes

- GitHub runner service should be running as `azureuser`.
- Azure auth should be performed in the runner user context, not in another shell user.
- The repo is ready for GitOps-style deployment through GitHub Actions + Helm + AKS.

## 9. Contact / maintainers

Use the Azure subscription owner identity and GitHub repo admin access to re-validate the runner if the VM is rebuilt or the service account changes.

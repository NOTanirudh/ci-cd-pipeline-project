# CI/CD Pipeline Project — Local Dev & Demo

This repository contains a small demo CI/CD monitoring dashboard (`cicd-dashboard`) and a demo backend/service (`user-service`).

The repo also includes a GitHub Actions workflow that builds frontend, runs tests, builds the `user-service` Docker image and pushes it to Docker Hub when credentials are configured.

This README covers how to run the demo stack locally, the required tools, and how the demo pipeline trigger works.

## Requirements

- Docker (Desktop or Engine)
- Docker Compose
- Git
- Node.js & npm (for the frontend)
- Python 3.10 and `pip` (for the `user-service`) — used by tests
- Optional: `kubectl` (if you want to test the Kubernetes deploy step)

If you're on Windows, the helper `scripts/dev-setup.ps1` will check for the above and show recommended Chocolatey commands.

## Run locally (quick)

This will build the `user-service` image and run Prometheus and Grafana so the dashboard has data sources to query.

1. Build & start services with Docker Compose

```pwsh
docker-compose up --build
```

2. Start the frontend (in a separate shell)

```pwsh
cd cicd-dashboard
npm install
npm start
```

The React app proxies API calls to `http://localhost:5000` (see `cicd-dashboard/package.json`). The `user-service` will be available at `http://localhost:5000` (as a container) and Prometheus at `http://localhost:9090`, Grafana at `http://localhost:3000`.

3. Open the dashboard at http://localhost:3000 if you reverse-proxy Grafana, or the frontend URL usually `http://localhost:3000` (React dev server). Use the `Set Repo & Run` button to trigger the demo pipeline — the backend `/api/trigger` will attempt a clone, run tests, perform a docker build, and (optionally) push the image and deploy to Kubernetes.

## How the demo trigger works

- The frontend calls `POST /api/trigger` with JSON `{ "repo": "owner/repo" }`.
- The `user-service`'s `/api/trigger` implements a synchronous demo pipeline:
  1. git clone (shallow)
  2. run tests (pytest for Python projects or `npm test` for Node projects)
  3. docker build (image tagged with short commit SHA)
  4. docker push (if `DOCKERHUB_USER`/`DOCKERHUB_PASS` env vars are set)
  5. kubectl set image (if `kubectl` and cluster are available)

This is a demo/demo-only flow — it's best-effort and intended for local testing. It expects `git`, `docker`, and optionally `kubectl` to be available on the host that runs the `user-service` container.

## CI/CD (GitHub Actions)

The workflow at `.github/workflows/ci-cd.yml`:
- checks out the repository
- builds & tests the React frontend
- builds & tests the Python `user-service`
- logs into Docker Hub and pushes an image (when `DOCKERHUB_USERNAME` / `DOCKERHUB_PASSWORD` secrets are set)

If you want the automated pipeline to build images and push to Docker Hub, add the appropriate secrets in your repository settings.

## Next steps I can implement for you

- Add a `make`/npm script to trigger the pipeline automatically from the host
- Improve the UI to show per-stage logs streaming
- Add a GitHub Action manual dispatch or API-friendly endpoint for remote triggers

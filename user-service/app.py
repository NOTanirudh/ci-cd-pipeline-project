from flask import Flask
from prometheus_client import Counter, generate_latest
from flask import jsonify
import os
import requests
import subprocess
import json
from datetime import datetime
from flask import request
import tempfile
import shutil
import time

app = Flask(__name__)
REQUESTS = Counter('http_requests_total', 'Total Requests')

@app.route('/')
def home():
    REQUESTS.inc()
    return "Hello from user-service!"

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain'}


@app.route('/api/dashboard')
def dashboard():
    """Return a small JSON summary for the frontend dashboard.

    This is intentionally simple: it exposes pipeline-like stage statuses and a
    few metrics (requests total). In a production setup you would aggregate
    this from your CI system or Prometheus queries.
    """
    # safe read of counter value (prometheus_client stores as _value)
    try:
        requests_total = int(REQUESTS._value.get())
    except Exception:
        requests_total = 0

    pipeline_stages = [
        {"id": 1, "name": "Code Checkout", "status": "success"},
        {"id": 2, "name": "Unit Testing", "status": "success", "testsPassed": 48, "testsFailed": 1},
        {"id": 3, "name": "Docker Build", "status": "success"},
        {"id": 4, "name": "Docker Push", "status": "success"},
        {"id": 5, "name": "Kubernetes Deploy", "status": "in_progress"}
    ]

    metrics = {
        "requestsPerSecond": None,
        "errorRate": 0.0,
        "cpuUsage": None,
        "memoryUsage": None,
        "requestsTotal": requests_total
    }

    return jsonify({"pipelineStages": pipeline_stages, "metrics": metrics})


@app.route('/api/overview')
def overview():
    """Aggregated overview that queries Prometheus for a few key metrics

    Environment variables:
      PROMETHEUS_URL - full URL to Prometheus server (default: http://prometheus:9090 or http://localhost:9090)

    This endpoint returns the existing pipeline stage data plus a small set
    of metrics so the frontend can present a single merged dashboard.
    """
    prom_url = os.environ.get('PROMETHEUS_URL') or os.environ.get('PROMETHEUS') or 'http://localhost:9090'

    def prom_query(q):
        try:
            resp = requests.get(f"{prom_url.rstrip('/')}/api/v1/query", params={'query': q}, timeout=5)
            resp.raise_for_status()
            body = resp.json()
            if body.get('status') != 'success':
                return None
            data = body.get('data', {})
            results = data.get('result', [])
            if not results:
                return None
            # pick first result value
            return float(results[0]['value'][1])
        except Exception:
            return None

    # compute real-ish pipeline stages (best-effort)
    try:
        requests_total = int(REQUESTS._value.get())
    except Exception:
        requests_total = 0

    # Helper: GitHub Actions status
    def github_actions_status():
        repo = os.environ.get('GITHUB_REPO')
        token = os.environ.get('GITHUB_TOKEN')
        if not repo or not token:
            return None
        try:
            url = f"https://api.github.com/repos/{repo}/actions/runs"
            resp = requests.get(url, params={'per_page': 1}, headers={'Authorization': f'token {token}'}, timeout=5)
            resp.raise_for_status()
            body = resp.json()
            runs = body.get('workflow_runs') or []
            if not runs:
                return None
            run = runs[0]
            status = run.get('status')
            conclusion = run.get('conclusion')
            html_url = run.get('html_url')
            if status in ('in_progress', 'queued'):
                return {'status': 'in_progress', 'detail': status, 'url': html_url}
            if status == 'completed':
                return {'status': 'success' if conclusion == 'success' else 'failed', 'detail': conclusion, 'url': html_url}
            return {'status': 'unknown', 'detail': status, 'url': html_url}
        except Exception:
            return None

    # Helper: Jenkins last build status
    def jenkins_status():
        jurl = os.environ.get('JENKINS_URL')
        job = os.environ.get('JENKINS_JOB')
        user = os.environ.get('JENKINS_USER')
        token = os.environ.get('JENKINS_TOKEN')
        if not jurl or not job:
            return None
        api = f"{jurl.rstrip('/')}/job/{job}/lastBuild/api/json"
        try:
            if user and token:
                resp = requests.get(api, auth=(user, token), timeout=5)
            else:
                resp = requests.get(api, timeout=5)
            resp.raise_for_status()
            b = resp.json()
            res = b.get('result')
            url = b.get('url')
            if res is None:
                return {'status': 'in_progress', 'detail': 'building', 'url': url}
            return {'status': 'success' if res == 'SUCCESS' else 'failed', 'detail': res, 'url': url}
        except Exception:
            return None

    # Helper: DockerHub tag existence (public)
    def dockerhub_status():
        repo = os.environ.get('DOCKERHUB_REPO')
        tag = os.environ.get('DOCKERHUB_TAG') or 'latest'
        if not repo:
            return None
        try:
            url = f"https://hub.docker.com/v2/repositories/{repo}/tags/{tag}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return {'status': 'success', 'detail': f'tag {tag} present', 'url': f'https://hub.docker.com/r/{repo}/tags'}
            if resp.status_code == 404:
                return {'status': 'in_progress', 'detail': f'tag {tag} not found', 'url': f'https://hub.docker.com/r/{repo}/tags'}
            return {'status': 'unknown', 'detail': f'status {resp.status_code}'}
        except Exception:
            return None

    # Helper: Kubernetes deployment status using kubectl (best-effort local demo)
    def kubernetes_deploy_status():
        dep = os.environ.get('K8S_DEPLOYMENT') or 'user-service'
        ns = os.environ.get('K8S_NAMESPACE') or 'default'
        kubectl = os.environ.get('KUBECTL_PATH') or 'kubectl'
        try:
            out = subprocess.check_output([kubectl, 'get', 'deployment', dep, '-n', ns, '-o', 'json'], stderr=subprocess.DEVNULL, timeout=5)
            j = json.loads(out)
            spec_replicas = j.get('spec', {}).get('replicas', 1)
            available = j.get('status', {}).get('availableReplicas', 0)
            updated = j.get('status', {}).get('updatedReplicas', 0)
            if available >= spec_replicas and updated >= spec_replicas:
                return {'status': 'success', 'detail': f'{available}/{spec_replicas} replicas available'}
            return {'status': 'in_progress', 'detail': f'{available}/{spec_replicas} replicas available'}
        except subprocess.CalledProcessError:
            return {'status': 'failed', 'detail': 'kubectl error or deployment not found'}
        except Exception:
            return None

    # Assemble pipeline stages using available status providers
    stages = []

    # 1) Source (GitHub repo)
    # repo can be provided by query param (UI) or environment variable
    gh_repo = request.args.get('repo') or os.environ.get('GITHUB_REPO')
    if gh_repo:
        stages.append({'id': 1, 'name': 'GitHub Repo', 'status': 'success', 'detail': gh_repo, 'url': f'https://github.com/{gh_repo}'})
    else:
        stages.append({'id': 1, 'name': 'GitHub Repo', 'status': 'unknown', 'detail': 'GITHUB_REPO not set'})

    # 2) CI Trigger (GitHub Actions preferred, else Jenkins)
    gha = github_actions_status()
    jnk = jenkins_status()
    if gha:
        stages.append({'id': 2, 'name': 'CI Trigger (GitHub Actions)', 'status': gha['status'], 'detail': gha.get('detail'), 'url': gha.get('url')})
    elif jnk:
        stages.append({'id': 2, 'name': 'CI Trigger (Jenkins)', 'status': jnk['status'], 'detail': jnk.get('detail'), 'url': jnk.get('url')})
    else:
        stages.append({'id': 2, 'name': 'CI Trigger', 'status': 'unknown', 'detail': 'No CI configured (set GITHUB_TOKEN or JENKINS_URL/JENKINS_JOB)'})

    # 3) Docker Build & Unit Tests — infer from CI status if possible
    docker_build_status = 'unknown'
    if gha and gha.get('status') == 'success':
        docker_build_status = 'success'
    elif gha and gha.get('status') == 'in_progress':
        docker_build_status = 'in_progress'
    elif jnk and jnk.get('status') == 'success':
        docker_build_status = 'success'
    elif jnk and jnk.get('status') == 'in_progress':
        docker_build_status = 'in_progress'
    stages.append({'id': 3, 'name': 'Docker Build & Unit Tests', 'status': docker_build_status})

    # 4) Push Docker Image to DockerHub
    dh = dockerhub_status()
    if dh:
        stages.append({'id': 4, 'name': 'Push to DockerHub', 'status': dh['status'], 'detail': dh.get('detail'), 'url': dh.get('url')})
    else:
        stages.append({'id': 4, 'name': 'Push to DockerHub', 'status': 'unknown', 'detail': 'DOCKERHUB_REPO not set or unreachable'})

    # 5) Deploy to Kubernetes
    k8s = kubernetes_deploy_status()
    if k8s:
        stages.append({'id': 5, 'name': 'Kubernetes Deploy', 'status': k8s.get('status'), 'detail': k8s.get('detail')})
    else:
        stages.append({'id': 5, 'name': 'Kubernetes Deploy', 'status': 'unknown', 'detail': 'kubectl not available or cluster unreachable'})

    # 6) Prometheus scrape
    prom_stage_status = 'unknown'
    prom_detail = None
    try:
        svc_up = prom_query('up{job="user-service"}')
        if svc_up is not None:
            prom_stage_status = 'success' if svc_up > 0 else 'in_progress'
            prom_detail = f'user-service up={svc_up}'
        else:
            prom_stage_status = 'unknown'
    except Exception:
        prom_stage_status = 'unknown'

    stages.append({'id': 6, 'name': 'Prometheus Scrape', 'status': prom_stage_status, 'detail': prom_detail})

    # 7) Grafana (link only)
    grafana_url = os.environ.get('GRAFANA_URL') or os.environ.get('REACT_APP_GRAFANA_URL')
    if grafana_url:
        stages.append({'id': 7, 'name': 'Grafana Dashboard', 'status': 'success', 'url': grafana_url})
    else:
        stages.append({'id': 7, 'name': 'Grafana Dashboard', 'status': 'unknown', 'detail': 'GRAFANA_URL not set'})

    # Metrics returned to frontend
    req_rate = prom_query('sum(rate(http_requests_total[5m]))')
    total_reqs = requests_total
    err_rate_val = None
    try:
        errs = prom_query('sum(rate(http_errors_total[5m]))')
        if errs is not None and req_rate:
            err_rate_val = (errs / req_rate) * 100.0 if req_rate != 0 else None
    except Exception:
        err_rate_val = None

    metrics = {
        'requestsPerSecond': req_rate,
        'requestsTotal': total_reqs,
        'errorRate': err_rate_val,
    }

    return jsonify({'pipelineStages': stages, 'metrics': metrics, 'prometheus': {'url': prom_url}})


def _run_cmd(cmd, cwd=None, timeout=600):
    """Run a shell command and return (returncode, stdout+stderr)."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, shell=False)
        out = proc.stdout.decode(errors='replace') if proc.stdout else ''
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return -1, 'command timed out'
    except Exception as e:
        return -1, f'error running command: {e}'


@app.route('/api/trigger', methods=['POST'])
def trigger():
    """Trigger a demo pipeline for the provided repo.

    Expects JSON body: { "repo": "owner/repo", "branch": "main" }

    This runs a synchronous sequence (clone -> tests -> docker build -> push -> deploy).
    It is best-effort and intended for demos/local use. Requires git, docker and kubectl on PATH.
    """
    body = request.get_json() or {}
    repo = body.get('repo') or request.args.get('repo')
    branch = body.get('branch') or 'main'
    if not repo:
        return jsonify({'error': 'repo is required (owner/repo)'}), 400

    tmp = tempfile.mkdtemp(prefix='pipeline_')
    stages = []
    start = time.time()

    try:
        # 1) Clone
        stages.append({'id': 1, 'name': 'Clone Repo', 'status': 'in_progress'})
        clone_url = f'https://github.com/{repo}.git'
        rc, out = _run_cmd(['git', 'clone', '--depth', '1', '--branch', branch, clone_url, tmp], cwd=None, timeout=120)
        stages[-1]['log'] = out
        stages[-1]['status'] = 'success' if rc == 0 else 'failed'
        if rc != 0:
            return jsonify({'pipelineStages': stages, 'metrics': {}, 'error': 'git clone failed'}), 200

        # detect commit sha
        rc, out = _run_cmd(['git', 'rev-parse', 'HEAD'], cwd=tmp)
        sha = out.strip() if rc == 0 else str(int(time.time()))

        # 2) Run Tests
        stages.append({'id': 2, 'name': 'Run Unit Tests', 'status': 'in_progress'})
        test_rc = 0
        test_out = ''
        # python project
        if os.path.exists(os.path.join(tmp, 'requirements.txt')) or os.path.exists(os.path.join(tmp, 'setup.py')):
            # install deps into virtualenv is out-of-scope; try running pytest directly if available
            rc, out = _run_cmd(['pytest', '-q'], cwd=tmp, timeout=300)
            test_rc = rc
            test_out = out
        # node project
        elif os.path.exists(os.path.join(tmp, 'package.json')):
            rc, out = _run_cmd(['npm', 'ci'], cwd=tmp, timeout=300)
            out_install = out
            rc2, out2 = _run_cmd(['npm', 'test', '--', '--watchAll=false'], cwd=tmp, timeout=300)
            test_rc = rc2
            test_out = out_install + '\n' + out2
        else:
            test_rc = 0
            test_out = 'no tests detected'

        stages[-1]['log'] = test_out
        stages[-1]['status'] = 'success' if test_rc == 0 else 'failed'
        if test_rc != 0:
            return jsonify({'pipelineStages': stages, 'metrics': {}, 'error': 'tests failed'}), 200

        # 3) Docker build
        stages.append({'id': 3, 'name': 'Docker Build', 'status': 'in_progress'})
        docker_repo = os.environ.get('DOCKERHUB_REPO') or (repo.split('/')[-1])
        tag = f'{docker_repo}:{sha[:7]}'
        rc, out = _run_cmd(['docker', 'build', '-t', tag, '.'], cwd=tmp, timeout=600)
        stages[-1]['log'] = out
        stages[-1]['status'] = 'success' if rc == 0 else 'failed'
        if rc != 0:
            return jsonify({'pipelineStages': stages, 'metrics': {}, 'error': 'docker build failed'}), 200

        # 4) Docker push (if credentials available)
        stages.append({'id': 4, 'name': 'Docker Push', 'status': 'in_progress'})
        dh_user = os.environ.get('DOCKERHUB_USER')
        dh_pass = os.environ.get('DOCKERHUB_PASS')
        pushed = False
        if dh_user and dh_pass:
            # tag with dockerhub namespace if provided
            dockerhub_repo = os.environ.get('DOCKERHUB_REPO')
            if dockerhub_repo:
                full_tag = f'{dockerhub_repo}:{sha[:7]}'
                _run_cmd(['docker', 'tag', tag, full_tag], cwd=tmp)
            else:
                full_tag = tag
            # login
            login_proc = subprocess.run(['docker', 'login', '--username', dh_user, '--password-stdin'], input=dh_pass.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            login_out = login_proc.stdout.decode(errors='replace')
            if login_proc.returncode == 0:
                rc2, out2 = _run_cmd(['docker', 'push', full_tag], cwd=tmp, timeout=600)
                stages[-1]['log'] = login_out + '\n' + out2
                stages[-1]['status'] = 'success' if rc2 == 0 else 'failed'
                pushed = (rc2 == 0)
            else:
                stages[-1]['log'] = login_out
                stages[-1]['status'] = 'failed'
        else:
            stages[-1]['log'] = 'DOCKERHUB_USER/DOCKERHUB_PASS not set — skipping push'
            stages[-1]['status'] = 'in_progress'

        # 5) Deploy to Kubernetes (best-effort)
        stages.append({'id': 5, 'name': 'Kubernetes Deploy', 'status': 'in_progress'})
        k8s_dep = os.environ.get('K8S_DEPLOYMENT') or repo.split('/')[-1]
        k8s_ns = os.environ.get('K8S_NAMESPACE') or 'default'
        # if pushed, set image to full_tag, else try to use local tag (minikube scenario requires image loaded)
        deploy_tag = full_tag if pushed else tag
        rc, out = _run_cmd(['kubectl', 'set', 'image', f'deployment/{k8s_dep}', f'{k8s_dep}={deploy_tag}', '-n', k8s_ns], cwd=None, timeout=90)
        stages[-1]['log'] = out
        stages[-1]['status'] = 'success' if rc == 0 else 'failed'

        # return final stages
        duration = time.time() - start
        metrics = {'durationSeconds': int(duration)}
        return jsonify({'pipelineStages': stages, 'metrics': metrics}), 200

    finally:
        try:
            shutil.rmtree(tmp)
        except Exception:
            pass


@app.route('/api/tools')
def tools():
    """Return a best-effort list of URLs for the external tools used by the pipeline.

    These are read from environment variables and translated into user-facing URLs.
    """
    prom = os.environ.get('PROMETHEUS_URL') or os.environ.get('PROMETHEUS') or 'http://localhost:9090'
    graf = os.environ.get('GRAFANA_URL') or os.environ.get('REACT_APP_GRAFANA_URL')
    docker_repo = os.environ.get('DOCKERHUB_REPO')
    docker_url = f'https://hub.docker.com/r/{docker_repo}' if docker_repo else None
    jenkins = os.environ.get('JENKINS_URL')
    github_repo = os.environ.get('GITHUB_REPO')
    github_url = f'https://github.com/{github_repo}' if github_repo else None

    return jsonify({
        'prometheus': prom,
        'grafana': graf,
        'dockerhub': docker_url,
        'jenkins': jenkins,
        'github': github_url
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

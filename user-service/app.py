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
from flask_cors import CORS

def trigger_github_workflow(repo, branch):
    """Trigger GitHub Actions workflow."""
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        return False, "GitHub token not configured"
        
    # Extract owner/repo from clone URL
    parts = repo.rstrip('.git').split('/')
    if len(parts) < 2:
        return False, "Invalid repository URL"
    owner_repo = '/'.join(parts[-2:])
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    url = f'https://api.github.com/repos/{owner_repo}/actions/workflows'
    
    try:
        # List workflows
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return False, f"Failed to list workflows: {response.text}"
            
        workflows = response.json()
        if not workflows.get('workflows'):
            return False, "No workflows found"
            
        # Trigger the first available workflow
        workflow_id = workflows['workflows'][0]['id']
        trigger_url = f'{url}/{workflow_id}/dispatches'
        
        data = {
            'ref': branch
        }
        
        response = requests.post(trigger_url, headers=headers, json=data)
        if response.status_code == 204:
            return True, "GitHub Actions workflow triggered successfully"
        return False, f"Failed to trigger workflow: {response.text}"
        
    except Exception as e:
        return False, str(e)

def trigger_jenkins_job(repo, branch):
    """Trigger Jenkins job."""
    jenkins_url = os.getenv('JENKINS_URL')
    jenkins_job = os.getenv('JENKINS_JOB')
    jenkins_token = os.getenv('JENKINS_TOKEN')
    
    if not all([jenkins_url, jenkins_job, jenkins_token]):
        return False, "Jenkins configuration incomplete"
        
    try:
        # Build URL with parameters
        params = {
            'token': jenkins_token,
            'GIT_REPO': repo,
            'GIT_BRANCH': branch
        }
        
        build_url = f'{jenkins_url}/job/{jenkins_job}/buildWithParameters'
        response = requests.post(build_url, params=params)
        
        if response.status_code == 201:
            return True, "Jenkins job triggered successfully"
        return False, f"Failed to trigger Jenkins job: {response.status_code}"
        
    except Exception as e:
        return False, str(e)
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
def get_ci_config():
    """Get CI configuration from environment variables."""
    return {
        'github_token': os.environ.get('GITHUB_TOKEN'),
        'jenkins_url': os.environ.get('JENKINS_URL'),
        'jenkins_job': os.environ.get('JENKINS_JOB'),
        'jenkins_user': os.environ.get('JENKINS_USER'),
        'jenkins_token': os.environ.get('JENKINS_TOKEN')
    }

def trigger_github_workflow(repo, branch):
    """Trigger GitHub Actions workflow via API."""
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        return None, "GitHub token not configured"
    
    try:
        # Trigger workflow_dispatch event
        owner, repo_name = repo.split('/')
        url = f"https://api.github.com/repos/{repo}/actions/workflows/ci-cd.yml/dispatches"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}",
        }
        data = {"ref": branch}
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 204:
            return True, "GitHub Actions workflow triggered successfully"
        return False, f"Failed to trigger workflow: {response.status_code}"
    except Exception as e:
        return False, f"Error triggering GitHub Actions: {str(e)}"

def trigger_jenkins_job(repo, branch):
    """Trigger Jenkins job via API."""
    jenkins_url = os.environ.get('JENKINS_URL')
    jenkins_job = os.environ.get('JENKINS_JOB')
    jenkins_user = os.environ.get('JENKINS_USER')
    jenkins_token = os.environ.get('JENKINS_TOKEN')
    
    if not all([jenkins_url, jenkins_job]):
        return None, "Jenkins URL/job not configured"
    
    try:
        # Trigger Jenkins build
        build_url = f"{jenkins_url.rstrip('/')}/job/{jenkins_job}/buildWithParameters"
        params = {
            'GITHUB_REPO': repo,
            'BRANCH': branch
        }
        
        auth = None
        if jenkins_user and jenkins_token:
            auth = (jenkins_user, jenkins_token)
        
        response = requests.post(build_url, params=params, auth=auth)
        if response.status_code in (201, 200):
            return True, "Jenkins job triggered successfully"
        return False, f"Failed to trigger Jenkins job: {response.status_code}"
    except Exception as e:
        return False, f"Error triggering Jenkins job: {str(e)}"

def trigger():
    """Trigger a pipeline for the provided repo.
    
    Expects JSON body: { "repo": "owner/repo", "branch": "main" }
    """
    body = request.get_json() or {}
    repo = body.get('repo') or request.args.get('repo')
    branch = body.get('branch') or 'main'
    
    if not repo:
        return jsonify({
            'pipelineStages': [{
                'id': 'error',
                'name': 'Input Validation',
                'status': 'failed',
                'detail': 'Repository (owner/repo) is required'
            }]
        }), 400

    print(f"Starting pipeline for repo: {repo} branch: {branch}")
    
    # Create temp dir for clone
    tmp = tempfile.mkdtemp(prefix='pipeline_')
    stages = []
    start = time.time()

    try:
        # 1. Clone Repository with validation
        stages.append({
            'id': 1,
            'name': 'Clone Repository',
            'status': 'in_progress',
            'detail': f'Cloning {repo} ({branch} branch)'
        })

        clone_url = f'https://github.com/{repo}.git'
        
        # Verify repository exists
        try:
            resp = requests.head(f'https://github.com/{repo}')
            if resp.status_code == 404:
                stages[-1].update({
                    'status': 'failed',
                    'detail': f'Repository {repo} not found on GitHub'
                })
                return jsonify({'pipelineStages': stages}), 200
        except Exception as e:
            print(f'GitHub check failed: {e}')
            
        # Attempt clone with detailed error capture
        rc, out = _run_cmd(['git', 'clone', '--depth', '1', '--branch', branch, clone_url, tmp])
        stages[-1]['log'] = out
        
        if rc != 0:
            error_detail = 'Unknown error'
            if 'repository not found' in out.lower():
                error_detail = 'Repository not found'
            elif 'could not resolve host' in out.lower():
                error_detail = 'Network error - could not reach GitHub'
            elif 'authentication failed' in out.lower():
                error_detail = 'Authentication failed'
            elif 'branch not found' in out.lower():
                error_detail = f'Branch {branch} not found'
                
            stages[-1].update({
                'status': 'failed',
                'detail': f'Clone failed: {error_detail}',
                'log': out
            })
            
            # Try to trigger CI instead
            stages.append({
                'id': 2,
                'name': 'CI Trigger',
                'status': 'in_progress',
                'detail': 'Attempting to trigger CI pipeline'
            })
            
            # Try GitHub Actions first
            github_success, github_msg = trigger_github_workflow(repo, branch)
            if github_success:
                stages[-1].update({
                    'status': 'success',
                    'detail': github_msg
                })
                return jsonify({'pipelineStages': stages}), 200
            
            # Fallback to Jenkins
            jenkins_success, jenkins_msg = trigger_jenkins_job(repo, branch)
            if jenkins_success:
                stages[-1].update({
                    'status': 'success',
                    'detail': jenkins_msg
                })
            else:
                stages[-1].update({
                    'status': 'failed',
                    'detail': f'CI not configured properly. Set GITHUB_TOKEN or JENKINS_URL/JENKINS_JOB. Details: {github_msg}, {jenkins_msg}'
                })
            
            return jsonify({'pipelineStages': stages}), 200

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

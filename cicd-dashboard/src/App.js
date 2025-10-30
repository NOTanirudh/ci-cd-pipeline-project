import React, { useState, useEffect } from 'react';

// Mock data simulating pipeline stages and monitoring metrics
const mockPipelineStages = [
  { id: 1, name: 'Code Checkout', status: 'success' },
  { id: 2, name: 'Unit Testing', status: 'success', testsPassed: 48, testsFailed: 1 },
  { id: 3, name: 'Docker Build', status: 'success' },
  { id: 4, name: 'Docker Push', status: 'success' },
  { id: 5, name: 'Kubernetes Deploy', status: 'in_progress' }
];

const mockMetrics = {
  requestsPerSecond: 98,
  errorRate: 0.7,
  cpuUsage: 55,
  memoryUsage: 63
};

const statusColors = {
  success: 'green',
  failed: 'red',
  in_progress: 'orange'
};

function PipelineStage({ stage }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      padding: '10px',
      borderBottom: '1px solid #ddd'
    }}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ fontWeight: 'bold' }}>{stage.name}</div>
        {stage.detail && <div style={{ color: '#666', fontSize: '0.85rem' }}>{stage.detail}</div>}
        {stage.url && <a href={stage.url} target="_blank" rel="noreferrer" style={{ color: '#007acc', fontSize: '0.85rem' }}>View</a>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <div style={{
          color: 'white',
          backgroundColor: statusColors[stage.status] || 'gray',
          borderRadius: '12px',
          padding: '6px 14px',
          fontWeight: 'bold',
          fontSize: '0.9rem'
        }}>
          {String(stage.status || 'unknown').replace('_', ' ').toUpperCase()}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, unit }) {
  return (
    <div style={{
      flex: 1,
      backgroundColor: '#f3f6f9',
      margin: '10px',
      padding: '20px',
      borderRadius: '8px',
      boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
      textAlign: 'center'
    }}>
      <div style={{ fontSize: '1.1rem', marginBottom: '8px', color: '#333' }}>{title}</div>
      <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#007acc' }}>
        {value}{unit}
      </div>
    </div>
  );
}

function App() {
  const [pipelineStages, setPipelineStages] = useState([]);
  const [metrics, setMetrics] = useState({});
  const [repoInput, setRepoInput] = useState('');
  const [selectedRepo, setSelectedRepo] = useState('');
  const [tools, setTools] = useState({});

  // Fetch merged overview data from backend on mount
  useEffect(() => {
    let mounted = true;
    const load = () => {
      const url = selectedRepo ? `/api/overview?repo=${encodeURIComponent(selectedRepo)}` : '/api/overview';
      fetch(url)
        .then(res => {
          if (!res.ok) throw new Error('Network response was not ok');
          return res.json();
        })
        .then(data => {
          if (!mounted) return;
          setPipelineStages(data.pipelineStages || []);
          setMetrics(data.metrics || {});
        })
        .catch(err => {
          console.error('Failed to fetch overview:', err);
        });
    };

    setPipelineStages([]);
    setMetrics({});
    // fetch tools list
    fetch('/api/tools')
      .then(r => r.ok ? r.json() : {})
      .then(data => setTools(data))
      .catch(() => {});

    load();
    const id = setInterval(load, 10000); // refresh every 10s
    return () => { mounted = false; clearInterval(id); };
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: '30px auto', fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif' }}>
      <h1 style={{ textAlign: 'center', color: '#004080' }}>CI/CD Pipeline Dashboard</h1>

      <div style={{ textAlign: 'center', marginBottom: 10 }}>
        <a href={process.env.REACT_APP_GRAFANA_URL || '/grafana'} target="_blank" rel="noreferrer" style={{ color: '#007acc' }}>Open Grafana</a>
      </div>

        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
        <input value={repoInput} onChange={e => setRepoInput(e.target.value)} placeholder="owner/repo (e.g. NOTanirudh/ci-cd-pipeline-project)" style={{ padding: 8, width: 400, marginRight: 8 }} />
        <button onClick={async () => {
            if (!repoInput) return;
            setSelectedRepo(repoInput);
            // call trigger endpoint to run pipeline
            try {
              const res = await fetch('/api/trigger', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ repo: repoInput }) });
              const data = await res.json();
              if (data.pipelineStages) {
                setPipelineStages(data.pipelineStages || []);
                setMetrics(data.metrics || {});
              }
            } catch (e) {
              console.error('trigger failed', e);
            }
          }} style={{ padding: '8px 12px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: 4 }}>Set Repo & Run</button>
      </div>

      {tools && (Object.keys(tools).length > 0) && (
        <section style={{ backgroundColor: '#fff9e6', borderRadius: 10, padding: 12, marginBottom: 16 }}>
          <h3 style={{ margin: '6px 0' }}>Tool URLs</h3>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {tools.github && <a href={tools.github} target="_blank" rel="noreferrer">GitHub</a>}
            {tools.jenkins && <a href={tools.jenkins} target="_blank" rel="noreferrer">Jenkins</a>}
            {tools.dockerhub && <a href={tools.dockerhub} target="_blank" rel="noreferrer">DockerHub</a>}
            {tools.prometheus && <a href={tools.prometheus} target="_blank" rel="noreferrer">Prometheus</a>}
            {tools.grafana && <a href={tools.grafana} target="_blank" rel="noreferrer">Grafana</a>}
          </div>
        </section>
      )}

      <section style={{ backgroundColor: 'white', borderRadius: 10, padding: 20, boxShadow: '0 3px 8px rgba(0,0,0,0.1)', marginBottom: 40 }}>
        <h2 style={{ borderBottom: '2px solid #007acc', paddingBottom: 6 }}>Pipeline Stages</h2>
        {pipelineStages.map(stage => (
          <PipelineStage key={stage.id} stage={stage} />
        ))}
      </section>

      <section style={{ display: 'flex', justifyContent: 'space-between', backgroundColor: 'white', padding: 20, borderRadius: 10, boxShadow: '0 3px 8px rgba(0,0,0,0.1)' }}>
        <MetricCard title="Requests/Second" value={metrics.requestsPerSecond ?? '—'} />
        <MetricCard title="Error Rate" value={metrics.errorRate ?? '—'} unit="%" />
        <MetricCard title="Requests Total" value={metrics.requestsTotal ?? '—'} />
        <MetricCard title="Prometheus" value={metrics.requestsPerSecond != null ? 'Connected' : 'Disconnected'} />
      </section>
    </div>
  );
}

export default App;

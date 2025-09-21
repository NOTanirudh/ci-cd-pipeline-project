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
      <div style={{ fontWeight: 'bold' }}>{stage.name}</div>
      <div style={{
        color: 'white',
        backgroundColor: statusColors[stage.status] || 'gray',
        borderRadius: '12px',
        padding: '4px 12px',
        fontWeight: 'bold',
        fontSize: '0.9rem'
      }}>
        {stage.status.replace('_', ' ').toUpperCase()}
      </div>
      {stage.testsPassed !== undefined && (
        <div style={{ marginLeft: '20px', color: '#555', fontSize: '0.85rem' }}>
          Tests Passed: {stage.testsPassed}, Failed: {stage.testsFailed}
        </div>
      )}
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

  // Simulate fetching data on mount
  useEffect(() => {
    setPipelineStages(mockPipelineStages);
    setMetrics(mockMetrics);
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: '30px auto', fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif' }}>
      <h1 style={{ textAlign: 'center', color: '#004080' }}>CI/CD Pipeline Dashboard</h1>

      <section style={{ backgroundColor: 'white', borderRadius: 10, padding: 20, boxShadow: '0 3px 8px rgba(0,0,0,0.1)', marginBottom: 40 }}>
        <h2 style={{ borderBottom: '2px solid #007acc', paddingBottom: 6 }}>Pipeline Stages</h2>
        {pipelineStages.map(stage => (
          <PipelineStage key={stage.id} stage={stage} />
        ))}
      </section>

      <section style={{ display: 'flex', justifyContent: 'space-between', backgroundColor: 'white', padding: 20, borderRadius: 10, boxShadow: '0 3px 8px rgba(0,0,0,0.1)' }}>
        <MetricCard title="Requests/Second" value={metrics.requestsPerSecond} />
        <MetricCard title="Error Rate" value={metrics.errorRate} unit="%" />
        <MetricCard title="CPU Usage" value={metrics.cpuUsage} unit="%" />
        <MetricCard title="Memory Usage" value={metrics.memoryUsage} unit="%" />
      </section>
    </div>
  );
}

export default App;

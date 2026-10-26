import React, {useState} from 'react';
import {FlaskConical} from 'lucide-react';
import {api} from './api';

export default function Performance() {
  const [result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function run() {
    setBusy(true);setError('');
    try {setResult(await api('/comparison'));} catch(e) {setError(e.message);} finally {setBusy(false);}
  }
  return <><div className="page-heading"><div className="eyebrow">LOCAL POLICY EXPERIMENT</div><h1>Compare admission policies.</h1><p>Run your backend’s deterministic limiter simulation.</p></div>
    <section className="panel"><h2>What this experiment measures</h2><p>A student sends a start request, 20 chunks, a status check, three repeated chunks and finalization, one request per simulated second. A separate fresh limiter sees 100 new-session attempts in ten simulated seconds.</p>
      <p>This is a limiter simulation, not an HTTP load test. It does not measure upload completion on disk, response latency or server capacity.</p>
      <button className="primary" disabled={busy} onClick={run}><FlaskConical size={17}/>{busy?'Running…':'Run policy comparison'}</button>
      {error&&<div className="error" role="alert">{error}</div>}
    </section>
    {result&&<><div className="table-wrap"><table><thead><tr><th>Policy</th><th>Student requests</th><th>Blocked decisions</th><th>All requests allowed?</th><th>Flood admissions / 100</th></tr></thead><tbody>{result.rows.map(r=><tr key={r.policy}><td>{r.policy}</td><td>{r.requests}</td><td>{r.blocked}</td><td>{r.finished?'Yes':'No'}</td><td>{r.flood_admissions}</td></tr>)}</tbody></table></div><p className="notice">{result.notes}</p></>}
  </>;
}

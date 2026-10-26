import React, {useEffect, useRef, useState} from 'react';
import {UploadCloud, CheckCircle2, Clock3, ShieldCheck, ChevronLeft, Play, Pause, Download, Wifi, WifiOff} from 'lucide-react';
import {api, date, label} from './api';

const mib = bytes => (bytes / (1024*1024)).toFixed(2);
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

export default function Upload({assignment:a, onBack, onDone}) {
  const [file,setFile]=useState(null), [session,setSession]=useState(a.session), [receipt,setReceipt]=useState(a.receipt);
  const [busy,setBusy]=useState(false), [message,setMessage]=useState(''), [error,setError]=useState('');
  const [demo,setDemo]=useState(true), [offline,setOffline]=useState(false), [autoBreak,setAutoBreak]=useState(false);
  const [log,setLog]=useState([]), [verified,setVerified]=useState(false);
  const control=useRef({paused:false,offline:false,abort:null});
  const mounted=useRef(true);
  useEffect(()=>()=>{mounted.current=false;control.current.paused=true;control.current.abort?.abort();},[]);
  const missing=new Set(session?.missing_chunks || []);
  const acknowledged=session ? session.total_chunks-missing.size : 0;
  const savedBytes=session ? Array.from({length:session.total_chunks},(_,i)=>i)
    .filter(i=>!missing.has(i)).reduce((sum,i)=>sum+Math.min(session.chunk_size,session.expected_size-i*session.chunk_size),0) : 0;
  const complete=Boolean(session && !missing.size);

  function record(text) {
    setLog(previous=>[{at:new Date().toLocaleTimeString(),text},...previous].slice(0,12));
  }
  function disconnect() {
    control.current.offline=true;
    control.current.paused=true;
    control.current.abort?.abort();
    setOffline(true);
    setVerified(false);
    setMessage('Demo disconnected. No more upload requests will be sent. Previously acknowledged chunks remain on the server.');
    record('Demo connection disabled. An in-flight request may need reconciliation on reconnect.');
  }
  async function reconnect() {
    setError('');
    try {
      if(session) {
        const status=await api('/uploads/'+session.id);
        setSession(status);
        record(`Server checked: ${status.total_chunks-status.missing_chunks.length} stored; ${status.missing_chunks.length} missing.`);
      }
      control.current.offline=false;
      setOffline(false);
      setVerified(true);
      setMessage('Connected. Server progress checked. Choose Resume upload to send only missing chunks.');
    } catch(e) {setError(e.message);}
  }
  async function run() {
    if(!file || control.current.offline) return;
    setBusy(true);setError('');control.current.paused=false;
    try {
      if(file.size>(a.max_file_size || 25*1024*1024) || !file.name.toLowerCase().endsWith('.pdf')) throw Error('Choose a PDF up to 25 MiB.');
      setMessage('Calculating the original file’s SHA-256…');
      const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
      const hash=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
      if(control.current.paused || control.current.offline) return;
      let current=session;
      if(current) {
        if(hash!==current.expected_hash || file.size!==current.expected_size) throw Error('Reselect exactly the same PDF used to start this session.');
        current=await api('/uploads/'+current.id);
      } else {
        current=await api('/uploads/start',{method:'POST',body:JSON.stringify({assignment_id:a.id,filename:file.name,expected_size:file.size,expected_hash:hash})});
      }
      setSession(current);setVerified(true);
      record(`Server reports ${current.missing_chunks.length} missing chunks of ${current.total_chunks}.`);
      for(const index of current.missing_chunks) {
        // Demonstration pacing delays real requests; it never advances progress.
        if(demo) await wait(1000);
        if(control.current.paused || control.current.offline || !mounted.current) return;
        setMessage(demo?'Uploading real chunks · demonstration pacing: 1 request/second':'Uploading real chunks…');
        const abort=new AbortController();control.current.abort=abort;
        await api(`/uploads/${current.id}/chunks/${index}`,{
          method:'PUT', body:file.slice(index*current.chunk_size,(index+1)*current.chunk_size),
          headers:{'Content-Type':'application/octet-stream'},signal:abort.signal
        });
        control.current.abort=null;
        current={...current,missing_chunks:current.missing_chunks.filter(i=>i!==index)};
        if(!mounted.current) return;
        setSession(current);
        record(`Chunk ${index+1}/${current.total_chunks} acknowledged by server.`);
        const remainingBytes=current.missing_chunks.reduce((sum,i)=>sum+Math.min(current.chunk_size,current.expected_size-i*current.chunk_size),0);
        if(demo && autoBreak && current.expected_size-remainingBytes>=12*1024*1024 && remainingBytes>0) {
          setAutoBreak(false);disconnect();return;
        }
      }
      setMessage('All chunks are stored. NOT submitted yet. Click Finalize submission to verify the PDF and issue a receipt.');
      record('All chunks acknowledged. Waiting for your explicit finalization.');
      onDone();
    } catch(e) {
      if(!mounted.current) return;
      if(e.name!=='AbortError') setError(e.message);
      setVerified(false);
      if(!control.current.offline) setMessage('Transfer interrupted. Resume will ask the server which chunks are missing.');
    } finally {
      control.current.abort=null;
      if(mounted.current) setBusy(false);
    }
  }
  async function finalize() {
    setBusy(true);setError('');setMessage('Verifying the full PDF and checking the server deadline…');
    try {
      const result=await api(`/uploads/${session.id}/finalize`,{method:'POST'});
      setReceipt(result);record('Server issued a '+label(result.status)+' receipt.');onDone();
    } catch(e) {setError(e.message);setMessage('No new receipt was confirmed. Check the error before retrying.');}
    finally {setBusy(false);}
  }
  async function cancel() {
    setError('');
    try {await api('/uploads/'+session.id,{method:'DELETE'});setSession(null);setLog([]);setMessage('Upload cancelled. A replacement must start before the deadline.');onDone();}
    catch(e) {setError(e.message);}
  }
  return <>
    <button className="back" disabled={busy} onClick={onBack}><ChevronLeft size={17}/>All assignments</button>
    <div className="page-heading"><div className="eyebrow">{a.course}</div><h1>{a.title}</h1><p>Assigned by {a.faculty}</p></div>
    <div className="upload-layout"><section className="panel">
      <h2>{receipt?'Submission confirmed':'Upload first. Finalize when ready.'}</h2><p>{a.description}</p>
      {receipt ? <div className="confirmed"><CheckCircle2 size={40}/><h3>Your work is safely submitted.</h3>
        <span className={'badge '+(receipt.status==='on_time'?'green':'amber')}>{label(receipt.status)}</span>
        <dl><dt>Submission ID</dt><dd>{receipt.id}</dd><dt>Server timestamp</dt><dd>{date(receipt.submitted_at)}</dd><dt>SHA-256 fingerprint</dt><dd className="hash">{receipt.final_hash}</dd></dl>
        <a className="primary" href={`/api/submissions/${receipt.id}/receipt`}><Download size={17}/>Download receipt</a>
      </div> : <>
        <section className="demo-controls" aria-label="Mentor demonstration controls">
          <div className="demo-control-heading"><strong>Mentor demonstration</strong><span className={'badge '+(offline?'amber':'green')}>{offline?'Demo disconnected':'Demo connected'}</span></div>
          <label className="check-label"><input type="checkbox" checked={demo} disabled={busy||offline} onChange={e=>setDemo(e.target.checked)}/>Slow real transfers to one chunk per second</label>
          <label className="check-label"><input type="checkbox" checked={autoBreak} disabled={!demo||offline} onChange={e=>setAutoBreak(e.target.checked)}/>Automatically disconnect after 12 MiB is acknowledged</label>
          <p>This is a labeled connection simulation. Wi-Fi off does not disconnect a server running on this same laptop (localhost). Chunks, storage and receipts are real.</p>
          <button className="secondary" disabled={offline&&busy} onClick={offline?reconnect:disconnect}>{offline?<Wifi size={16}/>:<WifiOff size={16}/>} {offline?'Reconnect & check server':'Disconnect demo connection'}</button>
        </section>
        <label className="file-zone"><UploadCloud size={33}/><strong>{file?file.name:'Choose your assignment PDF'}</strong>
          <span>{file?`${mib(file.size)} MiB`:'PDF only · up to 25 MiB · 200 pages'}</span>
          <input type="file" accept=".pdf,application/pdf" disabled={busy} onChange={e=>{setFile(e.target.files[0]||null);setError('');}}/>
        </label>
        <div className="sample-links"><strong>Sample PDFs for your demonstration</strong>
          <a href="/api/demo-files/20" download>20 MiB · 40 chunks <Download size={14}/></a>
          <a href="/api/demo-files/5" download>5 MiB · 10 chunks <Download size={14}/></a>
          <small>Valid PDFs with labeled test padding. At demo speed, 20 MiB takes about 40 seconds plus request time.</small>
        </div>
        {session && <div className="progress-area">
          <div><strong>{Math.round(100*savedBytes/session.expected_size)}% acknowledged</strong><span>{acknowledged} / {session.total_chunks} chunks</span></div>
          <progress value={savedBytes} max={session.expected_size}/>
          <div className="byte-summary"><span><strong>{mib(savedBytes)} MiB</strong> saved on server</span><span><strong>{mib(session.expected_size-savedBytes)} MiB</strong> remaining</span></div>
          <div className="chunk-grid" aria-label="Server acknowledged chunks">{Array.from({length:session.total_chunks},(_,i)=><span key={i} className={missing.has(i)?'chunk-cell missing':'chunk-cell saved'} title={`Chunk ${i+1}: ${missing.has(i)?'missing':'acknowledged'}`}>{i+1}</span>)}</div>
          <small>Green = acknowledged · outlined = missing. {verified?'Checked this session.':'Reconnect to reconcile any in-flight request.'}</small>
          <small>Recovery expires {date(session.expires_at)}</small><small>Session {session.id} · {complete?'all chunks stored; awaiting finalization':session.status}</small>
          <span className="badge amber">{complete?'READY TO FINALIZE — NOT SUBMITTED':'UPLOAD IN PROGRESS — NOT SUBMITTED'}</span>
        </div>}
        {message && <p role="status" className="notice">{message}</p>}{error && <div className="error" role="alert">{error}</div>}
        <div className="actions">
          {!complete && <button className="primary" disabled={busy||!file||offline} onClick={run}><Play size={17}/>{busy?'Transferring…':session?'Resume upload':'Start upload'}</button>}
          {complete && <button className="primary" disabled={busy||offline} onClick={finalize}><CheckCircle2 size={17}/>{busy?'Verifying…':'Finalize submission'}</button>}
          {busy&&!complete && <button className="secondary" onClick={()=>{control.current.paused=true;setMessage('Pausing after the in-flight chunk. Resume when ready.');}}><Pause size={16}/>Pause</button>}
          {session&&!busy && <button className="text-button" disabled={offline} onClick={cancel}>Cancel upload</button>}
        </div>
        {log.length>0 && <details className="transfer-log" open><summary>Real transfer activity</summary><ol>{log.map((entry,i)=><li key={i}><time>{entry.at}</time> {entry.text}</li>)}</ol></details>}
      </>}
    </section><section className="policy">
      <h3><Clock3 size={19}/>Deadline details</h3><dl><dt>Official deadline</dt><dd>{date(a.deadline_at)}</dd><dt>Recovery window</dt><dd>{a.recovery_minutes} minutes after deadline</dd></dl><hr/>
      <h3><ShieldCheck size={19}/>Show the recovery</h3><p>Use the 20 MiB sample. Enable automatic disconnect at 12 MiB, then start uploading. The grid will retain 24 green chunks and 16 missing chunks.</p>
      <p>Reconnect, resume the same PDF, and send only those missing chunks. Even at 100%, nothing is submitted until you click <strong>Finalize submission</strong>.</p>
      <p>To show grace recovery, faculty should set a deadline a few minutes ahead and five minutes of recovery. Start before it; finalize after it but before expiry.</p>
      <small>Demonstration pacing does not change server time or deadlines. A committed hash protects the file's integrity, not proof of when it was created.</small>
    </section></div>
  </>;
}

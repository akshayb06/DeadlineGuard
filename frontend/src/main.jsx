import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ShieldCheck, LayoutDashboard, FlaskConical, LogOut, ArrowRight, UploadCloud, FileText, Clock3, CheckCircle2, Download, Pause, Play, Plus, ChevronLeft, BookOpen} from 'lucide-react';
import './style.css';

import Upload from './Upload';
import Performance from './Performance';
import {api, date, label} from './api';
function remaining(deadline, now) {
    const mins=Math.ceil((deadline-now)/60);
    return mins<=0?'Deadline passed':mins<60?`${mins} min remaining`:mins<1440?`${Math.floor(mins/60)}h ${mins%60}m remaining`:`${Math.floor(mins/1440)} days remaining`;
}
function Badge({children, tone=''}) {return <span className={'badge '+tone}>{children}</span>;}
function App(){
 const [user,setUser]=useState(null),[ready,setReady]=useState(false),[page,setPage]=useState('dashboard'),[items,setItems]=useState([]),[receipts,setReceipts]=useState([]),[selected,setSelected]=useState(null),[error,setError]=useState(''),[now,setNow]=useState(Date.now()/1000);
 const offset=useRef(0);
 async function refresh(){
    try{
        const [data,rows]=await Promise.all([api('/assignments'),api('/submissions')]);
        setItems(data.assignments);
        setReceipts(rows);
        offset.current=data.server_time-Date.now()/1000;
        setNow(data.server_time);
    }catch(e){setError(e.message);}
}
 useEffect(()=>{
    api('/auth/me').then(setUser).catch(()=>{}).finally(()=>setReady(true));
    const timer=setInterval(()=>setNow(Date.now()/1000+offset.current),1000);
    return()=>clearInterval(timer);
},[]);
 useEffect(()=>{ if(user)refresh();},[user]);
    if(!ready)return <div className="loading">Opening your workspace…</div>;
    if(!user)return <Login onLogin={setUser}/>;
    async function logout(){
        try{await api('/auth/logout',{method:'POST'});
        setUser(null);
        setItems([]);
        setReceipts([]);
        setSelected(null);
        setPage('dashboard');
    }catch(e){setError(e.message);}}
    return <div className="app"><aside><a className="brand" href="#" onClick={e=>{e.preventDefault();setPage('dashboard');}}><ShieldCheck size={30}/><span>DeadlineGuard<small>ASSIGNMENT WORKSPACE</small></span></a><div className="workspace-label">YOUR WORKSPACE</div><nav><button className={page==='dashboard'?'active':''} onClick={()=>{setPage('dashboard');refresh();}}><LayoutDashboard size={18}/>{user.role==='faculty'?'Faculty overview':'My assignments'}</button><button className={page==='performance'?'active':''} onClick={()=>setPage('performance')}><FlaskConical size={18}/>Performance lab</button></nav><div className="sidebar-note"><ShieldCheck size={21}/><strong>Built for the final stretch.</strong><p>Interrupted uploads can resume within the assignment’s recovery window.</p></div><div className="profile"><span className="avatar">{user.username[0].toUpperCase()}</span><span><strong>{user.username}</strong><small>{user.role} account</small></span><button aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={18}/></button></div></aside><div className="main"><header><span>Academic workspace <span className="slash">/</span> {page==='performance'?'Performance lab':page==='upload'?'Submission':'Overview'}</span><Badge>LOCAL DEMO</Badge></header><main>{error&&<div role="alert" className="error">{error}<button onClick={()=>setError('')}>Dismiss</button></div>}{page==='performance'?<Performance/>:page==='upload'&&selected?<Upload assignment={selected} onBack={()=>{setPage('dashboard');refresh();}} onDone={refresh}/>:user.role==='faculty'?<Faculty items={items} receipts={receipts} refresh={refresh}/>:<><div className="page-heading"><div className="eyebrow">STUDENT WORKSPACE</div><h1>A little progress. A clear deadline.</h1><p>Welcome back, {user.username}. Here’s what’s coming up.</p></div><div className="summary"><div><span>Assignments</span><strong>{items.length.toString().padStart(2,'0')}</strong></div><div><span>Submitted</span><strong>{receipts.length.toString().padStart(2,'0')}</strong></div><div><span>In progress</span><strong>{items.filter(a=>a.session).length.toString().padStart(2,'0')}</strong></div><p><ShieldCheck size={22}/>Your uploads are saved in chunks.<br/>Pick up where you left off.</p></div><div className="section-title"><h2>Your assignments</h2><span>Demo courses · deadlines in your local time</span></div><div className="assignments">{items.map(a=><article className="assignment" key={a.id}><div className="course"><BookOpen size={17}/>{a.course}<Badge tone={a.receipt?'green':a.session?'amber':''}>{a.receipt?'Submitted':a.session?'In progress':a.deadline_at<=now?'Closed':'Not submitted'}</Badge></div><h3>{a.title}</h3><p>{a.description}</p><div className="assignment-bottom"><div><span><Clock3 size={15}/>{date(a.deadline_at)}</span><small>{remaining(a.deadline_at,now)} · {a.recovery_minutes} min recovery</small></div><button className="secondary" onClick={()=>{setSelected(a);setPage('upload');}}>{a.receipt?'View receipt':a.session?'Resume upload':'Open assignment'}<ArrowRight size={16}/></button></div></article>)}</div><ReceiptList receipts={receipts}/></>}</main><footer>DeadlineGuard <span>Trusted server time. Transparent submission records.</span></footer></div></div>;
}
function Login({onLogin}){
 const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function submit(e){
    e.preventDefault();
    setBusy(true);
    setError('');
    try{
        onLogin(await api('/auth/login',{method:'POST',body:JSON.stringify({username,password})}));
    }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <div className="login"><section className="login-story"><div className="brand"><ShieldCheck size={34}/><span>DeadlineGuard<small>ASSIGNMENT WORKSPACE</small></span></div><div><span className="eyebrow">LESS UNCERTAINTY. MORE FOCUS.</span><h1>Your work deserves<br/>a safe arrival.</h1><p>A clear path from your final edit to a confirmed submission—even when your connection has other plans.</p><div className="login-feature"><CheckCircle2/>Real submission receipts</div><div className="login-feature"><UploadCloud/>Uploads that pick up where you left off</div><div className="login-feature"><Clock3/>Clear deadlines and recovery windows</div></div><small>A university project · Local demonstration</small></section><section className="login-form"><form onSubmit={submit}><Badge>WELCOME TO YOUR WORKSPACE</Badge><h2>Sign in</h2><p>Continue to your assignments and submissions.</p>{error&&<div role="alert" className="error">{error}</div>}<label>Username<input required autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} placeholder="Enter your username"/></label><label>Password<input required autoComplete="current-password" type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password"/></label><button className="primary wide" disabled={busy}>{busy?'Signing in…':'Sign in'}<ArrowRight size={17}/></button><div className="demo"><strong>Try a demo account</strong><p>Seeded sample courses and accounts for evaluation.</p><div>{['student1','student2','faculty1'].map(name=><button type="button" key={name} onClick={()=>{setUsername(name);setPassword('pass1234');}}>{name==='faculty1'?'Faculty1':name==='student1'?'Student 1':'Student 2'}</button>)}</div><small>Password: pass1234</small></div></form></section></div>;
}
function ReceiptList({receipts}){return <section className="receipts"><div className="section-title"><h2>Submission receipts</h2><span>{receipts.length} confirmed</span></div>{!receipts.length?<div className="empty"><FileText size={24}/><div><strong>Your receipts will appear here</strong><p>Each confirmed submission includes its server timestamp and file hash.</p></div></div>:<div className="table-wrap"><table><thead><tr><th>Assignment / student</th><th>Submitted</th><th>Classification</th><th>Files</th></tr></thead><tbody>{receipts.map(r=><tr key={r.id}><td><strong>{r.title}</strong><small>{r.student}</small></td><td>{date(r.submitted_at)}</td><td><Badge tone={r.status==='on_time'?'green':'amber'}>{label(r.status)}</Badge></td><td><a href={`/api/submissions/${r.id}/download`}>PDF</a><a href={`/api/submissions/${r.id}/receipt`}>Receipt <Download size={13}/></a></td></tr>)}</tbody></table></div>}</section>;}
function Faculty({items,receipts,refresh}){
 const [open,setOpen]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function create(e){
    e.preventDefault();
    const form=e.currentTarget;
    const values=Object.fromEntries(new FormData(form));
    setBusy(true);
    setError('');
    try{
        await api('/assignments',{method:'POST',body:JSON.stringify({...values,recovery_minutes:Number(values.recovery_minutes),deadline_at:new Date(values.deadline_at).toISOString()})});
        form.reset();setOpen(false);await refresh();
    }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <><div className="page-heading heading-row"><div><div className="eyebrow">FACULTY WORKSPACE</div><h1>Clear expectations. Reliable records.</h1><p>Create assignments and follow your students’ submissions.</p></div><button className="primary" onClick={()=>setOpen(!open)}><Plus size={17}/>{open?'Close form':'New assignment'}</button></div>{open&&<form className="panel create-form" onSubmit={create}><h2>Create an assignment</h2>{error&&<div className="error">{error}</div>}<label>Assignment title<input name="title" required minLength={3} maxLength={140}/></label><label>Course<input name="course" required minLength={2} maxLength={100}/></label><label className="full">Instructions<textarea name="description" required maxLength={4000} rows={3}/></label><label>Deadline (your local time)<input type="datetime-local" name="deadline_at" required/></label><label>Recovery period in minutes<input type="number" name="recovery_minutes" min="0" max="60" defaultValue="5" required/></label><button className="primary" disabled={busy}>{busy?'Creating…':'Create assignment'}</button></form>}<div className="section-title"><h2>Assignments</h2><span>{items.length} total · seeded courses are demo data</span></div><div className="table-wrap"><table><thead><tr><th>Assignment</th><th>Deadline</th><th>Recovery</th><th>Submitted</th></tr></thead><tbody>{items.map(a=><tr key={a.id}><td><strong>{a.title}</strong><small>{a.course}</small></td><td>{date(a.deadline_at)}</td><td>{a.recovery_minutes} min</td><td>{receipts.filter(r=>r.assignment_id===a.id).length}</td></tr>)}</tbody></table></div><ReceiptList receipts={receipts}/></>;
}
createRoot(document.getElementById('root')).render(<App/>);

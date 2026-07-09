import React, {useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import axios from 'axios';
import {Mic, Square, Send, Volume2} from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App(){
  const [recording,setRecording]=useState(false);
  const [loading,setLoading]=useState(false);
  const [typed,setTyped]=useState('');
  const [transcript,setTranscript]=useState('');
  const [answer,setAnswer]=useState('');
  const mediaRecorder=useRef(null);
  const chunks=useRef([]);

  const playAudio=(b64)=>{
    if(!b64) return;
    const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
    audio.play();
  };

  const sendBlob=async(blob)=>{
    setLoading(true); setAnswer(''); setTranscript('');
    const fd = new FormData();
    fd.append('file', blob, 'voice.webm');
    try{
      const {data}=await axios.post(`${API}/voice`, fd);
      setTranscript(data.transcript); setAnswer(data.answer); playAudio(data.audio_base64);
    }catch(e){ setAnswer('Backend failed. Check FastAPI server and API keys.'); }
    finally{ setLoading(false); }
  };

  const start=async()=>{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    chunks.current=[];
    mediaRecorder.current=new MediaRecorder(stream);
    mediaRecorder.current.ondataavailable=e=>chunks.current.push(e.data);
    mediaRecorder.current.onstop=()=>{
      stream.getTracks().forEach(t=>t.stop());
      sendBlob(new Blob(chunks.current,{type:'audio/webm'}));
    };
    mediaRecorder.current.start(); setRecording(true);
  };

  const stop=()=>{ mediaRecorder.current?.stop(); setRecording(false); };

  const askText=async()=>{
    if(!typed.trim()) return;
    setLoading(true); setAnswer(''); setTranscript('');
    const fd = new FormData(); fd.append('text', typed);
    try{
      const {data}=await axios.post(`${API}/ask-text`, fd);
      setTranscript(data.transcript); setAnswer(data.answer); playAudio(data.audio_base64);
    }catch(e){ setAnswer('Backend failed. Check FastAPI server and API keys.'); }
    finally{ setLoading(false); }
  };

  return <main className="page">
    <section className="card">
      <div className="avatar"><div className={loading?'pulse face':'face'}>AI</div></div>
      <h1>Voice Web Assistant</h1>
      <p className="sub">Ask by voice. It uses live tools, guardrails, and speaks back.</p>

      <button className={recording?'mic stop':'mic'} onClick={recording?stop:start} disabled={loading}>
        {recording ? <Square/> : <Mic/>} {recording?'Stop':'Speak'}
      </button>

      <div className="or">or type a question</div>
      <div className="inputRow">
        <input value={typed} onChange={e=>setTyped(e.target.value)} placeholder="What's the weather in Hyderabad?" onKeyDown={e=>e.key==='Enter'&&askText()} />
        <button onClick={askText} disabled={loading}><Send size={18}/></button>
      </div>

      {loading && <p className="status">Thinking... tiny robot gears spinning.</p>}

      <div className="panel"><b>You</b><p>{transcript || 'No question yet.'}</p></div>
      <div className="panel"><b>Assistant</b><p>{answer || 'No answer yet.'}</p>{answer && <span className="speak"><Volume2 size={16}/> spoken response</span>}</div>
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<App/>);

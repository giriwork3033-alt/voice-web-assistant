import React, { useRef, useState, useCallback, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { createClient } from '@anam-ai/js-sdk';
import { AnamEvent } from '@anam-ai/js-sdk/dist/module/types';
import { Mic, Square, Send, Loader } from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const AVATAR_PLACEHOLDER =
  'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=480&h=480&fit=crop&crop=face';

function App() {
  const [phase, setPhase] = useState('idle');
  // idle | connecting | connected | listening | thinking | speaking | error
  const [transcript, setTranscript] = useState('');
  const [answer, setAnswer] = useState('');
  const [typed, setTyped] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [listening, setListening] = useState(false);

  const anamClientRef = useRef(null);
  const recognitionRef = useRef(null);
  const videoRef = useRef(null);

  const sessionActive = ['connected', 'listening', 'thinking', 'speaking'].includes(phase);

  /* ------------------------------------------------------------ */
  /*  Web Speech API — live transcription into the input field     */
  /* ------------------------------------------------------------ */
  const startListening = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser. Please use Chrome.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    let finalTranscript = '';

    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += text;
        } else {
          interim = text;
        }
      }
      // Show live words in the input field as the user speaks
      setTyped(finalTranscript + interim);
    };

    recognition.onend = () => {
      setListening(false);
      // Keep the final transcript in the input field for review/editing
      if (finalTranscript) {
        setTyped(finalTranscript);
      }
    };

    recognition.onerror = (event) => {
      console.warn('[Speech] Recognition error:', event.error);
      setListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, []);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setListening(false);
  }, []);

  /* ------------------------------------------------------------ */
  /*  Send question to backend, make avatar speak the answer       */
  /* ------------------------------------------------------------ */
  const sendQuestion = useCallback(async (question) => {
    if (!question.trim()) return;
    setTranscript(question);
    setAnswer('');
    setTyped('');
    setPhase('thinking');

    try {
      const fd = new FormData();
      fd.append('text', question);
      const res = await fetch(`${API}/ask-text`, { method: 'POST', body: fd });
      const data = await res.json();
      const text = data.answer || 'I could not generate a response.';
      setAnswer(text);
      setPhase('speaking');

      // Make the avatar speak (Anam handles TTS + lip-sync)
      if (anamClientRef.current) {
        anamClientRef.current.talk(text);
      }

      // Return to connected after a reasonable time
      setTimeout(() => setPhase((p) => (p === 'speaking' ? 'connected' : p)), 10000);
    } catch (err) {
      console.error('[Backend]', err);
      setAnswer('Something went wrong. Please try again.');
      setPhase('connected');
    }
  }, []);

  const handleSend = () => {
    if (!typed.trim()) return;
    sendQuestion(typed.trim());
  };

  /* ------------------------------------------------------------ */
  /*  Start Anam avatar session                                    */
  /* ------------------------------------------------------------ */
  const startSession = useCallback(async () => {
    setPhase('connecting');
    setErrorMsg('');
    try {
      const tokenRes = await fetch(`${API}/anam/session-token`, { method: 'POST' });
      const tokenData = await tokenRes.json();
      if (tokenData.error) throw new Error(tokenData.error);

      const client = createClient(tokenData.sessionToken, {
        // We handle mic input ourselves via Web Speech API for live
        // transcription — Anam only renders the avatar and speaks
        disableInputAudio: true,
      });
      anamClientRef.current = client;

      client.addListener(AnamEvent.CONNECTION_ESTABLISHED, () => {
        setPhase('connected');
      });

      client.addListener(AnamEvent.CONNECTION_CLOSED, () => {
        setPhase('idle');
        anamClientRef.current = null;
      });

      if (videoRef.current) {
        await client.streamToVideoAndAudioElements('avatar-video', 'avatar-audio');
      }
    } catch (err) {
      console.error('[Anam]', err);
      setErrorMsg(err.message || 'Connection failed');
      setPhase('error');
    }
  }, []);

  /* ---- cleanup ---- */
  useEffect(() => {
    return () => {
      if (anamClientRef.current) {
        try { anamClientRef.current.stopStreaming(); } catch (e) { /* */ }
      }
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (e) { /* */ }
      }
    };
  }, []);

  /* ---- status label ---- */
  const statusLabel = {
    idle: null,
    connecting: 'Connecting to avatar...',
    connected: 'Ready',
    listening: 'Listening — speak now...',
    thinking: 'Thinking...',
    speaking: null,
    error: errorMsg || 'Something went wrong',
  }[phase];

  const statusColor = {
    connecting: '#f0a030',
    connected: '#4CAF50',
    listening: '#2196F3',
    thinking: '#f0a030',
    error: '#f44336',
  }[phase] || '#aaa';

  /* ================================================================ */
  return (
    <main className="page">
      <section className="card">
        {/* ---- AVATAR ---- */}
        <div className="avatar-container">
          <video
            id="avatar-video"
            ref={videoRef}
            autoPlay
            playsInline
            className={`avatar-video ${sessionActive ? 'visible' : ''}`}
          />
          <audio id="avatar-audio" autoPlay style={{ display: 'none' }} />
          {!sessionActive && (
            <img src={AVATAR_PLACEHOLDER} alt="AI Assistant" className="avatar-placeholder" />
          )}
          {phase === 'thinking' && (
            <div className="avatar-overlay">
              <Loader size={28} className="spin" />
            </div>
          )}
        </div>

        {/* ---- TITLE ---- */}
        <h1>Voice Web Assistant</h1>

        {/* ---- STATUS ---- */}
        {statusLabel && (
          <p className="status" style={{ color: statusColor }}>{statusLabel}</p>
        )}

        {/* ---- BEFORE SESSION: SPEAK BUTTON starts Anam session ---- */}
        {phase === 'idle' && (
          <button className="mic" onClick={startSession}>
            <Mic /> Speak
          </button>
        )}
        {phase === 'connecting' && (
          <button className="mic" disabled>
            <Loader size={18} className="spin" /> Connecting...
          </button>
        )}
        {phase === 'error' && (
          <button className="mic" onClick={startSession}>
            <Mic /> Try Again
          </button>
        )}

        {/* ---- AFTER SESSION: MIC + INPUT + SEND ---- */}
        {sessionActive && (
          <div className="input-area">
            {/* Mic button for voice input */}
            <button
              className={`mic-inline ${listening ? 'active' : ''}`}
              onClick={listening ? stopListening : startListening}
              disabled={phase === 'thinking' || phase === 'speaking'}
              title={listening ? 'Stop listening' : 'Start listening'}
            >
              {listening ? <Square size={18} /> : <Mic size={18} />}
            </button>

            {/* Live transcription / typed input field */}
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={listening ? 'Listening...' : 'Type or speak your question'}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={phase === 'thinking' || phase === 'speaking'}
              className={listening ? 'input-listening' : ''}
            />

            {/* Send button */}
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={!typed.trim() || phase === 'thinking' || phase === 'speaking'}
              title="Send question"
            >
              <Send size={18} />
            </button>
          </div>
        )}

        {/* ---- TRANSCRIPT & ANSWER ---- */}
        {(transcript || answer) && (
          <>
            <div className="panel">
              <b>You</b>
              <p>{transcript}</p>
            </div>
            <div className="panel">
              <b>Assistant</b>
              <p>{answer || (phase === 'thinking' ? 'Thinking...' : '')}</p>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);

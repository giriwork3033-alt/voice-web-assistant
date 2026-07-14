import React, { useRef, useState, useCallback, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { Mic, Square, Send, Loader, Volume2 } from 'lucide-react';
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
  const [listening, setListening] = useState(false);
  const [avatarMode, setAvatarMode] = useState('anam'); // 'anam' | 'fallback'
  const [fallbackNotice, setFallbackNotice] = useState('');

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
      setTyped(finalTranscript + interim);
    };

    recognition.onend = () => {
      setListening(false);
      if (finalTranscript) setTyped(finalTranscript);
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
    if (recognitionRef.current) recognitionRef.current.stop();
    setListening(false);
  }, []);

  /* ------------------------------------------------------------ */
  /*  Fallback: play Edge-TTS audio from backend directly          */
  /* ------------------------------------------------------------ */
  const playAudioFallback = (base64) => {
    if (!base64) return;
    const audio = new Audio(`data:audio/mpeg;base64,${base64}`);
    audio.onended = () => setPhase('connected');
    audio.play().catch(() => setPhase('connected'));
  };

  /* ------------------------------------------------------------ */
  /*  Send question to backend, make avatar (or fallback) respond  */
  /* ------------------------------------------------------------ */
  /* ------------------------------------------------------------ */
  /*  Stop the avatar / audio mid-speech                           */
  /* ------------------------------------------------------------ */
  const stopSpeaking = useCallback(() => {
    // Stop Anam avatar if active
    if (anamClientRef.current) {
      try { anamClientRef.current.stopSpeaking?.(); } catch (e) { /* */ }
    }
    // Stop any fallback audio
    document.querySelectorAll('audio').forEach((el) => {
      el.pause();
      el.currentTime = 0;
    });
    setPhase('connected');
  }, []);

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

      if (avatarMode === 'anam' && anamClientRef.current) {
        // Photorealistic avatar speaks with lip-sync
        anamClientRef.current.talk(text);
        setTimeout(() => setPhase((p) => (p === 'speaking' ? 'connected' : p)), 10000);
      } else {
        // Fallback: play Edge-TTS audio from the backend response
        playAudioFallback(data.audio_base64);
      }
    } catch (err) {
      console.error('[Backend]', err);
      setAnswer('Something went wrong. Please try again.');
      setPhase('connected');
    }
  }, [avatarMode]);

  const handleSend = () => {
    if (!typed.trim()) return;
    sendQuestion(typed.trim());
  };

  /* ------------------------------------------------------------ */
  /*  Start session: try Anam first, fall back gracefully          */
  /* ------------------------------------------------------------ */
  const startSession = useCallback(async () => {
    setPhase('connecting');
    setFallbackNotice('');

    try {
      // Dynamically import Anam SDK (only loaded if needed)
      const { createClient } = await import('@anam-ai/js-sdk');
      const { AnamEvent } = await import('@anam-ai/js-sdk/dist/module/types');

      const tokenRes = await fetch(`${API}/anam/session-token`, { method: 'POST' });
      const tokenData = await tokenRes.json();
      if (tokenData.error) throw new Error(tokenData.error);

      const client = createClient(tokenData.sessionToken, {
        disableInputAudio: true,
      });
      anamClientRef.current = client;

      client.addListener(AnamEvent.CONNECTION_ESTABLISHED, () => {
        setAvatarMode('anam');
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
      console.warn('[Anam] Avatar unavailable, using audio fallback:', err.message);
      anamClientRef.current = null;
      setAvatarMode('fallback');
      setFallbackNotice(
        err.message?.includes('usage limit') || err.message?.includes('upgrade')
          ? 'Avatar credits exhausted — using voice-only mode'
          : 'Avatar temporarily unavailable — using voice-only mode'
      );
      setPhase('connected');
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
    connecting: 'Connecting...',
    connected: 'Ready',
    listening: 'Listening — speak now...',
    thinking: 'Thinking...',
    speaking: null,
    error: 'Something went wrong',
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
            className={`avatar-video ${sessionActive && avatarMode === 'anam' ? 'visible' : ''}`}
          />
          <audio id="avatar-audio" autoPlay style={{ display: 'none' }} />
          {!(sessionActive && avatarMode === 'anam') && (
            <img src={AVATAR_PLACEHOLDER} alt="AI Assistant" className="avatar-placeholder" />
          )}
          {phase === 'thinking' && (
            <div className="avatar-overlay">
              <Loader size={28} className="spin" />
            </div>
          )}
          {phase === 'speaking' && avatarMode === 'fallback' && (
            <div className="avatar-overlay speaking-overlay">
              <Volume2 size={28} className="pulse-icon" />
            </div>
          )}
        </div>

        {/* ---- TITLE ---- */}
        <h1>Voice Web Assistant</h1>

        {/* ---- FALLBACK NOTICE ---- */}
        {fallbackNotice && (
          <p className="fallback-notice">{fallbackNotice}</p>
        )}

        {/* ---- STATUS ---- */}
        {statusLabel && (
          <p className="status" style={{ color: statusColor }}>{statusLabel}</p>
        )}

        {/* ---- SPEAK BUTTON (before session) ---- */}
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

        {/* ---- STOP BUTTON (during speaking) ---- */}
        {phase === 'speaking' && (
          <button className="mic stop" onClick={stopSpeaking}>
            <Square size={18} /> Stop
          </button>
        )}

        {/* ---- MIC + INPUT + SEND (after session) ---- */}
        {sessionActive && (
          <div className="input-area">
            <button
              className={`mic-inline ${listening ? 'active' : ''}`}
              onClick={listening ? stopListening : startListening}
              disabled={phase === 'thinking' || phase === 'speaking'}
              title={listening ? 'Stop listening' : 'Start listening'}
            >
              {listening ? <Square size={18} /> : <Mic size={18} />}
            </button>

            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={listening ? 'Listening...' : 'Type or speak your question'}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={phase === 'thinking' || phase === 'speaking'}
              className={listening ? 'input-listening' : ''}
            />

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

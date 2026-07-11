import React, { useRef, useState, useEffect, useCallback } from 'react';
import { createClient } from '@anam-ai/js-sdk';
import { AnamEvent } from '@anam-ai/js-sdk/dist/module/types';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Anam photorealistic avatar panel.
 *
 * Architecture:
 *   Anam handles: avatar video rendering, lip-sync, TTS (speaks the response)
 *   Our backend handles: guardrails, LLM + tool calling (Groq), answer generation
 *
 * Flow:
 *   1. User types or speaks (Anam captures mic if enabled)
 *   2. Transcript sent to our /ask-text endpoint (guardrails + Groq + tools)
 *   3. Text answer returned (no audio needed — Anam does its own TTS)
 *   4. anamClient.talk(answer) makes the avatar speak the response
 */
export default function AnamAvatarPanel() {
  const videoRef = useRef(null);
  const anamClientRef = useRef(null);
  const [status, setStatus] = useState('idle');
  const [transcript, setTranscript] = useState('');
  const [answer, setAnswer] = useState('');
  const [typed, setTyped] = useState('');
  const [loading, setLoading] = useState(false);
  const processingRef = useRef(false);

  const startSession = useCallback(async () => {
    setStatus('connecting');
    try {
      // Step 1: Get a session token from our backend (keeps API key server-side)
      const tokenRes = await fetch(`${API}/anam/session-token`, { method: 'POST' });
      const tokenData = await tokenRes.json();
      if (tokenData.error) throw new Error(tokenData.error);

      // Step 2: Initialize the Anam client with the session token
      const client = createClient(tokenData.sessionToken, {
        disableInputAudio: false, // Let Anam capture mic for STT
      });
      anamClientRef.current = client;

      // Step 3: Listen for user messages from Anam's built-in STT
      client.addListener(AnamEvent.MESSAGE_HISTORY_UPDATED, async (messages) => {
        if (processingRef.current) return;
        // Find the latest user message
        const userMessages = messages.filter(m => m.role === 'user');
        if (userMessages.length === 0) return;
        const latestUser = userMessages[userMessages.length - 1];
        if (!latestUser.content) return;
        await processQuestion(latestUser.content, client);
      });

      client.addListener(AnamEvent.CONNECTION_ESTABLISHED, () => {
        console.log('[Anam] Connection established');
        setStatus('connected');
      });

      client.addListener(AnamEvent.CONNECTION_CLOSED, () => {
        console.log('[Anam] Connection closed');
        setStatus('idle');
      });

      // Step 4: Start streaming avatar video to the video element
      if (videoRef.current) {
        await client.streamToVideoAndAudioElements(
          videoRef.current.id,
          'anam-audio-element'
        );
      }
    } catch (err) {
      console.error('[Anam] Session failed:', err);
      setStatus('error: ' + err.message);
    }
  }, []);

  const processQuestion = async (question, client) => {
    if (processingRef.current) return;
    processingRef.current = true;
    setLoading(true);
    setTranscript(question);
    setAnswer('');

    try {
      // Send to our backend (guardrails + Groq LLM + tools)
      const fd = new FormData();
      fd.append('text', question);
      const res = await fetch(`${API}/ask-text`, { method: 'POST', body: fd });
      const data = await res.json();
      const answerText = data.answer || 'I could not generate a response.';
      setAnswer(answerText);

      // Make the avatar speak the response (Anam handles TTS + lip-sync)
      if (client || anamClientRef.current) {
        const c = client || anamClientRef.current;
        c.talk(answerText);
      }
    } catch (err) {
      console.error('[Anam] Backend call failed:', err);
      setAnswer('Backend failed. Please try again.');
    } finally {
      setLoading(false);
      processingRef.current = false;
    }
  };

  const handleTypedSubmit = async () => {
    if (!typed.trim() || !anamClientRef.current) return;
    await processQuestion(typed.trim(), anamClientRef.current);
    setTyped('');
  };

  const stopSession = useCallback(() => {
    if (anamClientRef.current) {
      anamClientRef.current.stopStreaming();
      anamClientRef.current = null;
    }
    setStatus('idle');
  }, []);

  useEffect(() => {
    return () => {
      if (anamClientRef.current) {
        anamClientRef.current.stopStreaming();
      }
    };
  }, []);

  return (
    <main className="page">
      <section className="card">
        {/* Avatar video */}
        <div style={{ position: 'relative', width: '100%', maxWidth: 480, margin: '0 auto' }}>
          <video
            id="anam-video-element"
            ref={videoRef}
            autoPlay
            playsInline
            style={{
              width: '100%',
              borderRadius: 16,
              background: '#000',
              display: status === 'connected' ? 'block' : 'none',
            }}
          />
          <audio id="anam-audio-element" autoPlay style={{ display: 'none' }} />
          {status !== 'connected' && (
            <div className="avatar">
              <div className="face">AI</div>
            </div>
          )}
        </div>

        <h1>Voice Web Assistant</h1>
        <p className="sub">Ask by voice. It uses live tools, guardrails, and speaks back.</p>

        {/* Session controls */}
        {status === 'idle' && (
          <button className="mic" onClick={startSession}>
            Start Avatar Session
          </button>
        )}
        {status === 'connecting' && <p className="status">Connecting to avatar...</p>}
        {status === 'connected' && (
          <>
            <p className="status" style={{ color: '#4CAF50' }}>
              Avatar connected — speak into your mic or type below
            </p>
            <button className="mic stop" onClick={stopSession}>
              End Session
            </button>
          </>
        )}
        {status.startsWith('error') && (
          <>
            <p className="status" style={{ color: '#f44336' }}>{status}</p>
            <button className="mic" onClick={startSession}>Retry</button>
          </>
        )}

        {/* Typed input (works alongside voice) */}
        {status === 'connected' && (
          <>
            <div className="or">or type a question</div>
            <div className="inputRow">
              <input
                value={typed}
                onChange={e => setTyped(e.target.value)}
                placeholder="What's the weather in Hyderabad?"
                onKeyDown={e => e.key === 'Enter' && handleTypedSubmit()}
                disabled={loading}
              />
              <button onClick={handleTypedSubmit} disabled={loading}>
                Send
              </button>
            </div>
          </>
        )}

        {loading && <p className="status">Thinking...</p>}

        <div className="panel"><b>You</b><p>{transcript || 'No question yet.'}</p></div>
        <div className="panel"><b>Assistant</b><p>{answer || 'No answer yet.'}</p></div>
      </section>
    </main>
  );
}

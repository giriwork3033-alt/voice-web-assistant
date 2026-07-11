import React from 'react';
import { createRoot } from 'react-dom/client';
import AnamAvatarPanel from './components/AnamAvatarPanel';
import './style.css';

function App() {
  return <AnamAvatarPanel />;
}

createRoot(document.getElementById('root')).render(<App />);

import React from 'react';
import ReactDOM from 'react-dom/client';
import ChatWidget from './chat/ChatWidget';
import './index.css';

const container = document.getElementById('chatbot-root');

if (container) {
  ReactDOM.createRoot(container).render(
    <React.StrictMode>
      <ChatWidget />
    </React.StrictMode>
  );
}

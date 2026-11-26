import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
// Self-hosted (fontsource): the Workfield renders fully offline, matching
// the "nothing leaves this computer" promise — no runtime calls to a font
// CDN. Latin + Latin Extended covers English and Italian; the other 20-odd
// scripts fontsource ships by default are skipped to keep the bundle lean.
import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import '@fontsource/ibm-plex-sans/latin-700.css';
import '@fontsource/ibm-plex-sans/latin-400-italic.css';
import '@fontsource/ibm-plex-sans/latin-600-italic.css';
import '@fontsource/ibm-plex-sans/latin-ext-400.css';
import '@fontsource/ibm-plex-sans/latin-ext-500.css';
import '@fontsource/ibm-plex-sans/latin-ext-600.css';
import '@fontsource/ibm-plex-sans/latin-ext-700.css';
import '@fontsource/ibm-plex-sans/latin-ext-400-italic.css';
import '@fontsource/ibm-plex-sans/latin-ext-600-italic.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import '@fontsource/ibm-plex-mono/latin-600.css';
import '@fontsource/ibm-plex-mono/latin-ext-400.css';
import '@fontsource/ibm-plex-mono/latin-ext-500.css';
import '@fontsource/ibm-plex-mono/latin-ext-600.css';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('Piko application root is missing');
createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);

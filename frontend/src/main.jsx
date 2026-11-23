import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// No StrictMode: it would open two WebSocket sessions in development.
createRoot(document.getElementById('root')).render(<App />)

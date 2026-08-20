import { useState } from 'react';
import { Settings, Server, Key, Save, CheckCircle } from 'lucide-react';
import { getBaseURL, getApiKey, setBaseURL, setApiKey } from '../api/client';

export default function SettingsPage() {
  const [url, setUrl] = useState(getBaseURL());
  const [apiKey, setKey] = useState(getApiKey());
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setBaseURL(url);
    setApiKey(apiKey);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-xl font-bold text-text-main mb-1">Settings</h1>
      <p className="text-text-secondary text-sm mb-6">Configure server connection</p>

      <div className="max-w-lg space-y-5">
        <div>
          <label className="flex items-center gap-2 text-text-main text-sm font-medium mb-2">
            <Server size={14} /> Server URL
          </label>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="http://localhost:8090"
            className="w-full bg-input-bg border border-border rounded-xl px-4 py-2.5 text-text-main text-sm focus:outline-none focus:border-primary placeholder:text-text-muted"
          />
        </div>

        <div>
          <label className="flex items-center gap-2 text-text-main text-sm font-medium mb-2">
            <Key size={14} /> API Key (optional)
          </label>
          <input
            value={apiKey}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Leave empty if not required"
            type="password"
            className="w-full bg-input-bg border border-border rounded-xl px-4 py-2.5 text-text-main text-sm focus:outline-none focus:border-primary placeholder:text-text-muted"
          />
        </div>

        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl text-sm font-medium hover:bg-primary-dark transition-colors"
        >
          {saved ? <CheckCircle size={16} /> : <Save size={16} />}
          {saved ? 'Saved!' : 'Save Settings'}
        </button>

        <div className="mt-8 pt-6 border-t border-border">
          <h2 className="text-text-main text-sm font-semibold mb-2 flex items-center gap-2">
            <Settings size={14} /> About
          </h2>
          <div className="text-text-secondary text-sm space-y-1">
            <p>BigTree Web Client v1.0.0</p>
            <p>Connects to BigTree RAG Bot public API</p>
          </div>
        </div>
      </div>
    </div>
  );
}

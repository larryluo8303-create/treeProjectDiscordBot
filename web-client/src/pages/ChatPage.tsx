import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Camera, Leaf, Bookmark, Loader2, ImagePlus } from 'lucide-react';
import { useSendMessage, useAnalyzeImage, type ChatMessage } from '../api/hooks';
import { saveCurrentSession, saveBookmark, type ChatSession } from '../utils/storage';
import { confidenceColor, confidenceBg, formatTime } from '../utils/helpers';

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sessionId] = useState(() => Date.now().toString(36));
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sendMutation = useSendMessage();
  const visionMutation = useAnalyzeImage();
  const isBusy = sendMutation.isPending || visionMutation.isPending;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (messages.length === 0) return;
    const firstUser = messages.find((m) => m.role === 'user');
    const session: ChatSession = {
      id: sessionId,
      title: firstUser?.content.slice(0, 40) || 'New Chat',
      messages,
      createdAt: messages[0]?.timestamp || Date.now(),
      updatedAt: Date.now(),
    };
    saveCurrentSession(session);
  }, [messages, sessionId]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isBusy) return;

    const userMsg: ChatMessage = { role: 'user', content: text, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');

    const history = messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    sendMutation.mutate(
      { message: text, conversation_history: history },
      {
        onSuccess: (data) => {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: data.answer, confidence: data.confidence, sources: data.sources, timestamp: Date.now() },
          ]);
        },
        onError: () => {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: '抱歉，无法连接到服务器，请稍后重试。', timestamp: Date.now() },
          ]);
        },
      },
    );
  }, [input, messages, isBusy, sendMutation]);

  const handleImageUpload = useCallback(
    (file: File) => {
      if (isBusy) return;
      const url = URL.createObjectURL(file);
      const userMsg: ChatMessage = {
        role: 'user',
        content: input.trim() || '📸 Chart uploaded for analysis',
        imageUrl: url,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      const captionText = input.trim();
      setInput('');

      visionMutation.mutate(
        { file, text: captionText },
        {
          onSuccess: (data) => {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: data.answer, confidence: data.confidence, timestamp: Date.now() },
            ]);
          },
          onError: () => {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: '抱歉，图片分析失败，请稍后重试。', timestamp: Date.now() },
            ]);
          },
        },
      );
    },
    [input, isBusy, visionMutation],
  );

  const handleBookmark = useCallback(
    (msg: ChatMessage) => {
      const prevUser = [...messages].reverse().find((m) => m.role === 'user' && m.timestamp < msg.timestamp);
      saveBookmark({
        id: Date.now().toString(36),
        question: prevUser?.content || '(image analysis)',
        answer: msg.content,
        confidence: msg.confidence || 0,
        savedAt: Date.now(),
      });
    },
    [messages],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Empty state
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col">
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/20 flex items-center justify-center mb-4">
            <Leaf size={32} className="text-primary" />
          </div>
          <h1 className="text-2xl font-bold text-text-main mb-2">BigTree Chat</h1>
          <p className="text-text-secondary text-sm mb-8">Ask questions or upload charts for analysis</p>
          <div className="flex flex-wrap gap-2 justify-center max-w-md">
            {['ES今天怎么看？', '什么是中枢？', '如何判断趋势？'].map((s) => (
              <button
                key={s}
                onClick={() => setInput(s)}
                className="px-4 py-2 rounded-full border border-border bg-surface text-primary text-sm hover:bg-surface-light transition-colors"
              >
                {s}
              </button>
            ))}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-2 rounded-full border border-warning bg-surface text-warning text-sm hover:bg-surface-light transition-colors flex items-center gap-1.5"
            >
              <ImagePlus size={14} /> Upload a chart
            </button>
          </div>
        </div>
        {/* Input bar */}
        <div className="border-t border-border bg-surface p-3 flex items-end gap-2">
          <input type="file" ref={fileInputRef} accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && handleImageUpload(e.target.files[0])} />
          <button onClick={() => fileInputRef.current?.click()} className="p-2.5 rounded-full text-primary hover:bg-surface-light transition-colors">
            <Camera size={20} />
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            rows={1}
            maxLength={2000}
            className="flex-1 bg-input-bg border border-border rounded-2xl px-4 py-2.5 text-text-main text-sm resize-none focus:outline-none focus:border-primary placeholder:text-text-muted"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isBusy}
            className="p-2.5 rounded-full bg-primary text-white disabled:opacity-40 hover:bg-primary-dark transition-colors"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return (
            <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                  isUser
                    ? 'bg-user-bubble text-white rounded-br-sm'
                    : 'bg-bot-bubble border border-border rounded-bl-sm'
                }`}
              >
                {!isUser && (
                  <div className="flex items-center gap-2 mb-1.5">
                    <Leaf size={14} className="text-success" />
                    <span className="text-success text-xs font-semibold">BigTree</span>
                    {msg.confidence !== undefined && (
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${confidenceBg(msg.confidence)} ${confidenceColor(msg.confidence)}`}>
                        {msg.confidence}/10
                      </span>
                    )}
                    <button onClick={() => handleBookmark(msg)} className="ml-auto p-0.5 text-text-muted hover:text-warning transition-colors" title="Bookmark">
                      <Bookmark size={13} />
                    </button>
                  </div>
                )}
                {isUser && msg.imageUrl && (
                  <img src={msg.imageUrl} alt="uploaded chart" className="w-full max-h-48 object-cover rounded-lg mb-2" />
                )}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                <p className="text-text-muted text-[10px] mt-1 text-right">{formatTime(msg.timestamp)}</p>
              </div>
            </div>
          );
        })}
        {isBusy && (
          <div className="flex items-center gap-2 px-2">
            <Loader2 size={16} className="text-primary animate-spin" />
            <span className="text-text-secondary text-sm">
              {visionMutation.isPending ? 'Analyzing chart...' : 'BigTree is thinking...'}
            </span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-border bg-surface p-3 flex items-end gap-2">
        <input type="file" ref={fileInputRef} accept="image/*" className="hidden" onChange={(e) => { if (e.target.files?.[0]) handleImageUpload(e.target.files[0]); e.target.value = ''; }} />
        <button onClick={() => fileInputRef.current?.click()} disabled={isBusy} className="p-2.5 rounded-full text-primary hover:bg-surface-light transition-colors disabled:text-text-muted">
          <Camera size={20} />
        </button>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question..."
          rows={1}
          maxLength={2000}
          className="flex-1 bg-input-bg border border-border rounded-2xl px-4 py-2.5 text-text-main text-sm resize-none focus:outline-none focus:border-primary placeholder:text-text-muted"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isBusy}
          className="p-2.5 rounded-full bg-primary text-white disabled:opacity-40 hover:bg-primary-dark transition-colors"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}

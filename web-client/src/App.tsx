import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import {
  MessageSquare, Activity, Search, CalendarDays, FileText,
  HelpCircle, Bookmark, History, GraduationCap, Settings, Newspaper,
} from 'lucide-react';
import ChatPage from './pages/ChatPage';
import DigestPage from './pages/DigestPage';
import SearchPage from './pages/SearchPage';
import EventsPage from './pages/EventsPage';
import FAQPage from './pages/FAQPage';
import BookmarksPage from './pages/BookmarksPage';
import HistoryPage from './pages/HistoryPage';
import LessonsArchivePage from './pages/LessonsArchivePage';
import NewsPage from './pages/NewsPage';
import SummariesPage from './pages/SummariesPage';
import SettingsPage from './pages/SettingsPage';

const navItems = [
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/news', icon: Newspaper, label: 'News' },
  { to: '/summaries', icon: FileText, label: 'Summaries' },
  { to: '/digest', icon: Activity, label: 'Digest' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/events', icon: CalendarDays, label: 'Events' },
  { to: '/faq', icon: HelpCircle, label: 'FAQ' },
  { to: '/bookmarks', icon: Bookmark, label: 'Bookmarks' },
  { to: '/history', icon: History, label: 'History' },
  { to: '/lessons', icon: GraduationCap, label: 'Lessons' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function App() {
  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-16 lg:w-56 bg-surface border-r border-border flex flex-col shrink-0">
        <div className="p-3 lg:p-4 border-b border-border flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white font-bold text-sm shrink-0">
            BT
          </div>
          <span className="hidden lg:block text-text-main font-semibold text-sm">BigTree</span>
        </div>
        <nav className="flex-1 py-2 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 lg:px-4 py-2.5 mx-1 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-primary/15 text-primary'
                    : 'text-text-secondary hover:bg-surface-light hover:text-text-main'
                }`
              }
            >
              <Icon size={20} className="shrink-0 mx-auto lg:mx-0" />
              <span className="hidden lg:block">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <p className="hidden lg:block text-text-muted text-[10px] text-center">BigTree v1.0.0</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/summaries" element={<SummariesPage />} />
          <Route path="/digest" element={<DigestPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/faq" element={<FAQPage />} />
          <Route path="/bookmarks" element={<BookmarksPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/lessons" element={<LessonsArchivePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

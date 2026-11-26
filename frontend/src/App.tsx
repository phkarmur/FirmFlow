import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { DashboardPage } from './pages/DashboardPage';
import { TasksPage } from './pages/TasksPage';
import { ClientsPage } from './pages/ClientsPage';
import { ServicesPage } from './pages/ServicesPage';
import { ReportsPage } from './pages/ReportsPage';
import { TeamPage } from './pages/TeamPage';
import { LoginPage } from './pages/LoginPage';
import { SettingsPage } from './pages/SettingsPage';
import { ProfilePage } from './pages/ProfilePage';
import { BatchesPage } from './pages/BatchesPage';
import { enableColumnResize } from './components/columnResize';
import { ResetPasswordPage, ForcePasswordChange } from './pages/PasswordPages';

const MainLayout: React.FC = () => {
  const { user, loading } = useAuth();
  // Phone / tablet: the sidebar opens as a drawer from the menu button
  const [navOpen, setNavOpen] = React.useState(false);
  // Every table: drag the vertical bar in the header to resize a column
  React.useEffect(() => enableColumnResize(), []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white font-semibold">
        Starting FirmFlow Practice System...
      </div>
    );
  }

  if (!user) {
    // Link from the password-reset e-mail works without a session
    if (window.location.pathname === '/reset-password') return <ResetPasswordPage />;
    return <LoginPage />;
  }
  if (user.must_change_password) {
    return <ForcePasswordChange />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <Navbar onMenu={() => setNavOpen(true)} />
      <div className="flex flex-1">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-5 sm:py-6 w-full min-w-0 transition-all">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/clients" element={<ClientsPage />} />
            <Route path="/services" element={<ServicesPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/team" element={<TeamPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/batches" element={<BatchesPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <MainLayout />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;

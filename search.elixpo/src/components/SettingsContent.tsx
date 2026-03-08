'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  User, Shield, Palette, Globe, Zap, Bell,
  ChevronLeft, LogIn, LogOut, Trash2, ExternalLink,
} from 'lucide-react';
import { useAuth, type AuthUser } from '@/hooks/useAuth';

type Section = 'account' | 'preferences' | 'notifications';

const NAV_ITEMS: { id: Section; label: string; icon: typeof User }[] = [
  { id: 'account', label: 'Account', icon: User },
  { id: 'preferences', label: 'Preferences', icon: Palette },
  { id: 'notifications', label: 'Notifications', icon: Bell },
];

export default function SettingsContent() {
  const router = useRouter();
  const { user, loading, login, logout, refetch } = useAuth();
  const [activeSection, setActiveSection] = useState<Section>('account');

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#18191a]">
        <div className="text-[#555] text-sm">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#18191a]">
        <div className="flex flex-col items-center text-center max-w-sm">
          <div className="w-16 h-16 rounded-full bg-[#232425] flex items-center justify-center mb-6">
            <User size={28} className="text-[#555]" />
          </div>
          <h2 className="text-xl font-semibold text-white mb-2">Sign in to access your profile</h2>
          <p className="text-[#888] text-sm mb-8">
            Save your preferences, access your library across devices, and get unlimited searches.
          </p>
          <button
            onClick={() => login('/profile')}
            className="flex items-center gap-2 px-6 py-3 bg-lime-main text-black rounded-xl font-medium text-sm hover:bg-lime-light transition-colors"
          >
            <LogIn size={18} />
            Sign in with Elixpo
          </button>
          <button
            onClick={() => router.push('/')}
            className="mt-4 text-[#888] text-sm hover:text-white transition-colors"
          >
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex bg-[#18191a]">
      {/* Settings left nav */}
      <aside className="w-[220px] h-full bg-[#171717] border-r border-[#2a2b2d] flex flex-col shrink-0">
        {/* Back to Home */}
        <button
          onClick={() => router.push('/')}
          className="flex items-center gap-1.5 px-4 pt-5 pb-3 text-sm text-[#999] hover:text-white transition-colors"
        >
          <ChevronLeft size={16} />
          Home
        </button>

        {/* Nav sections */}
        <nav className="px-3 flex flex-col gap-0.5 mt-2">
          <p className="px-3 text-[#666] text-xs font-medium mb-2">Account</p>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveSection(item.id)}
              className={`
                w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-colors
                ${activeSection === item.id
                  ? 'text-white bg-[#2a2b2d]'
                  : 'text-[#999] hover:text-white hover:bg-[#222]'}
              `}
            >
              <item.icon size={16} />
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      {/* Content area */}
      <main className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-2xl px-10 py-10">
          {activeSection === 'account' && (
            <AccountSection user={user} onUpdate={refetch} onLogout={logout} />
          )}
          {activeSection === 'preferences' && (
            <PreferencesSection user={user} onUpdate={refetch} />
          )}
          {activeSection === 'notifications' && (
            <NotificationsSection />
          )}
        </div>
      </main>
    </div>
  );
}

// ── Account Section ─────────────────────────────────────────────────────────

function AccountSection({
  user, onUpdate, onLogout,
}: { user: AuthUser; onUpdate: () => void; onLogout: () => void }) {
  const [saving, setSaving] = useState(false);
  const [bio, setBio] = useState(user.bio || '');
  const [location, setLocation] = useState(user.location || '');
  const [website, setWebsite] = useState(user.website || '');
  const [company, setCompany] = useState(user.company || '');
  const [jobTitle, setJobTitle] = useState(user.jobTitle || '');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await fetch('/api/user/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bio, location, website, company, jobTitle }),
      });
      onUpdate();
    } finally {
      setSaving(false);
    }
  }, [bio, location, website, company, jobTitle, onUpdate]);

  const handleDelete = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    await fetch('/api/user/profile', { method: 'DELETE' });
    onLogout();
  };

  return (
    <>
      <h2 className="text-xl font-semibold text-white font-display mb-6">Account</h2>

      {/* Avatar row */}
      <Row
        label={
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full overflow-hidden shrink-0">
              {user.avatar ? (
                <img src={user.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full bg-[#333] flex items-center justify-center text-white text-sm font-medium">
                  {(user.displayName || user.email)[0].toUpperCase()}
                </div>
              )}
            </div>
            <span className="text-white text-sm">{user.displayName || user.email.split('@')[0]}</span>
          </div>
        }
      />

      {/* Info rows */}
      <Row label="Full Name" value={user.displayName || '-'} />
      <Row label="Email" value={user.email} badge={user.emailVerified ? 'Verified' : undefined} />
      <Row label="Tier" value={user.tier} badgeColor="lime" />

      {/* Divider */}
      <div className="h-px bg-[#2a2b2d] my-6" />

      {/* Profile fields */}
      <h3 className="text-lg font-semibold text-white mb-4">Profile</h3>
      <div className="space-y-4">
        <Field label="Bio" value={bio} onChange={setBio} placeholder="Tell us about yourself" multiline maxLength={500} />
        <Field label="Location" value={location} onChange={setLocation} placeholder="City, Country" />
        <Field label="Website" value={website} onChange={setWebsite} placeholder="https://..." />
        <Field label="Company" value={company} onChange={setCompany} placeholder="Where you work" />
        <Field label="Job title" value={jobTitle} onChange={setJobTitle} placeholder="What you do" />
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="mt-5 px-6 py-2.5 bg-[#2a2b2d] hover:bg-[#333] text-white text-sm font-medium rounded-lg border border-[#333] transition-colors disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Save changes'}
      </button>

      <div className="h-px bg-[#2a2b2d] my-6" />

      {/* Usage stats */}
      <h3 className="text-lg font-semibold text-white mb-4">Usage</h3>
      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard label="Searches" value={user.totalSearches} />
        <StatCard label="Sessions" value={user.totalSessions} />
        <StatCard label="Member since" value={user.memberSince ? new Date(user.memberSince).toLocaleDateString('en', { month: 'short', year: 'numeric' }) : '-'} />
      </div>

      <div className="h-px bg-[#2a2b2d] my-6" />

      {/* System */}
      <h3 className="text-lg font-semibold text-white mb-4">System</h3>
      <Row label="Connected account" value={`Elixpo Accounts \u00b7 ${user.email}`} badge="Connected" badgeColor="sage" />
      <Row
        label={<span className="text-[#ccc]">You are signed in as {user.displayName || user.email.split('@')[0]}</span>}
        action={
          <button
            onClick={onLogout}
            className="px-4 py-1.5 text-sm border border-[#333] rounded-lg text-[#ccc] hover:text-white hover:border-[#555] transition-colors"
          >
            Sign out
          </button>
        }
      />
      <Row
        label={<span className="text-red-400">Delete account</span>}
        action={
          <button
            onClick={handleDelete}
            className={`px-4 py-1.5 text-sm border rounded-lg transition-colors ${
              confirmDelete
                ? 'border-red-500/40 text-red-400 bg-red-500/10 hover:bg-red-500/20'
                : 'border-[#333] text-red-400 hover:border-red-500/40'
            }`}
          >
            {confirmDelete ? 'Confirm delete' : 'Delete'}
          </button>
        }
      />
    </>
  );
}

// ── Preferences Section ─────────────────────────────────────────────────────

function PreferencesSection({ user, onUpdate }: { user: AuthUser; onUpdate: () => void }) {
  const [saving, setSaving] = useState(false);

  const updatePref = useCallback(async (field: string, value: string | number | boolean) => {
    setSaving(true);
    try {
      await fetch('/api/user/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      });
      onUpdate();
    } finally {
      setSaving(false);
    }
  }, [onUpdate]);

  return (
    <>
      <h2 className="text-xl font-semibold text-white font-display mb-6">Preferences</h2>

      <h3 className="text-lg font-semibold text-white mb-4">Search</h3>
      <SelectRow
        label="Default region"
        value={user.searchRegion}
        options={[
          { value: 'auto', label: 'Auto-detect' },
          { value: 'us', label: 'United States' },
          { value: 'gb', label: 'United Kingdom' },
          { value: 'de', label: 'Germany' },
          { value: 'fr', label: 'France' },
          { value: 'jp', label: 'Japan' },
          { value: 'in', label: 'India' },
        ]}
        onChange={(v) => updatePref('searchRegion', v)}
      />
      <SelectRow
        label="Safe search"
        value={String(user.safeSearch)}
        options={[
          { value: '0', label: 'Off' },
          { value: '1', label: 'Moderate' },
          { value: '2', label: 'Strict' },
        ]}
        onChange={(v) => updatePref('safeSearch', parseInt(v))}
      />
      <ToggleRow
        label="Deep search by default"
        description="Use thorough multi-source search for every query"
        checked={user.deepSearchDefault}
        onChange={(v) => updatePref('deepSearchDefault', v)}
      />

      <div className="h-px bg-[#2a2b2d] my-6" />

      <h3 className="text-lg font-semibold text-white mb-4">Language & Region</h3>
      <SelectRow
        label="Language"
        value={user.language}
        options={[
          { value: 'en', label: 'English' },
          { value: 'es', label: 'Spanish' },
          { value: 'fr', label: 'French' },
          { value: 'de', label: 'German' },
          { value: 'ja', label: 'Japanese' },
          { value: 'zh', label: 'Chinese' },
          { value: 'hi', label: 'Hindi' },
        ]}
        onChange={(v) => updatePref('language', v)}
      />

      {saving && <p className="text-xs text-[#666] mt-4">Saving...</p>}
    </>
  );
}

// ── Notifications Section ───────────────────────────────────────────────────

function NotificationsSection() {
  return (
    <>
      <h2 className="text-xl font-semibold text-white font-display mb-6">Notifications</h2>
      <p className="text-[#888] text-sm">Notification preferences coming soon.</p>
    </>
  );
}

// ── Shared components ───────────────────────────────────────────────────────

function Row({
  label, value, badge, badgeColor, action,
}: {
  label: React.ReactNode; value?: string; badge?: string;
  badgeColor?: 'lime' | 'sage'; action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between py-3.5 border-b border-[#2a2b2d]/60">
      <div className="flex flex-col gap-0.5">
        {typeof label === 'string' ? (
          <span className="text-[#888] text-sm">{label}</span>
        ) : label}
        {value && <span className="text-white text-sm">{value}</span>}
      </div>
      <div className="flex items-center gap-2">
        {badge && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            badgeColor === 'lime'
              ? 'bg-lime-dim text-lime-main border border-lime-border'
              : 'bg-sage-dim text-sage-main border border-sage-border'
          }`}>
            {badge}
          </span>
        )}
        {action}
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, placeholder, multiline, maxLength,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; multiline?: boolean; maxLength?: number;
}) {
  const cls = "w-full bg-[#111] border border-[#2a2b2d] rounded-lg px-4 py-2.5 text-white text-sm placeholder-[#555] focus:outline-none focus:border-[#444] transition-colors";
  return (
    <div>
      <label className="text-[#888] text-sm mb-1.5 block">{label}</label>
      {multiline ? (
        <textarea
          value={value} onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder} maxLength={maxLength} rows={3}
          className={`${cls} resize-none`}
        />
      ) : (
        <input
          type="text" value={value} onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder} className={cls}
        />
      )}
    </div>
  );
}

function SelectRow({
  label, value, options, onChange,
}: {
  label: string; value: string;
  options: { value: string; label: string }[]; onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between py-3.5 border-b border-[#2a2b2d]/60">
      <span className="text-[#ccc] text-sm">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-[#1a1a1a] border border-[#333] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none cursor-pointer"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function ToggleRow({
  label, description, checked, onChange,
}: {
  label: string; description?: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-3.5 border-b border-[#2a2b2d]/60">
      <div>
        <span className="text-[#ccc] text-sm">{label}</span>
        {description && <p className="text-[#555] text-xs mt-0.5">{description}</p>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`w-11 h-6 rounded-full transition-colors relative shrink-0 ${checked ? 'bg-lime-main' : 'bg-[#333]'}`}
      >
        <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${checked ? 'left-[22px]' : 'left-0.5'}`} />
      </button>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="p-4 bg-[#111] rounded-xl border border-[#2a2b2d] text-center">
      <p className="text-white text-lg font-semibold font-display">{value}</p>
      <p className="text-[#888] text-xs mt-1">{label}</p>
    </div>
  );
}

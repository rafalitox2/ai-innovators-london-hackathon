import React, { useEffect, useState } from 'react';
import { GitHubAuthConfig, GitHubUser, TeamMemberProfile } from '../types/auth';
import {
  FALLBACK_TEAM_ROSTER,
  fetchGitHubAuthConfig,
  fetchGitHubPublicProfile,
  fetchTeamRoster
} from '../services/authService';

interface GitHubAuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoginSuccess: (user: GitHubUser) => void;
}

export const GitHubAuthModal: React.FC<GitHubAuthModalProps> = ({
  isOpen,
  onClose,
  onLoginSuccess
}) => {
  const [team, setTeam] = useState<TeamMemberProfile[]>(FALLBACK_TEAM_ROSTER);
  const [config, setConfig] = useState<GitHubAuthConfig | null>(null);
  const [customUsername, setCustomUsername] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchTeamRoster().then(setTeam);
      fetchGitHubAuthConfig().then(setConfig);
      setError(null);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSelectTeamMember = async (member: TeamMemberProfile) => {
    setLoading(true);
    setError(null);
    try {
      const user = await fetchGitHubPublicProfile(member.username);
      onLoginSuccess(user);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Error authenticating with GitHub profile');
    } finally {
      setLoading(false);
    }
  };

  const handleCustomLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customUsername.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const user = await fetchGitHubPublicProfile(customUsername.trim());
      onLoginSuccess(user);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to authenticate user');
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthRedirect = () => {
    if (!config?.client_id) return;
    const rawRedirect = config.redirect_uri || '/ui';
    const fullRedirect = /^https?:\/\//i.test(rawRedirect)
      ? rawRedirect
      : `${window.location.origin}${rawRedirect.startsWith('/') ? '' : '/'}${rawRedirect}`;
    const redirect = encodeURIComponent(fullRedirect);
    const scope = encodeURIComponent('read:user user:email');
    window.location.href = `https://github.com/login/oauth/authorize?client_id=${encodeURIComponent(
      config.client_id
    )}&redirect_uri=${redirect}&scope=${scope}`;
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(11, 13, 20, 0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px'
      }}
    >
      <div
        className="dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="github-auth-dialog-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '560px',
          maxHeight: '90dvh',
          overflowY: 'auto',
          background: 'var(--color-bg)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--color-border)',
          boxShadow: '0 24px 48px rgba(0, 0, 0, 0.6), 0 0 0 1px var(--color-section-ghost)',
          padding: '28px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px'
        }}
      >
        {/* Modal Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '8px',
                background: 'var(--color-section)',
                border: '1px solid var(--color-accent-700)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              {/* GitHub Octocat SVG */}
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ color: 'var(--color-accent)' }}
              >
                <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
                <path d="M9 18c-4.51 2-5-2-7-2" />
              </svg>
            </div>
            <div>
              <div
                style={{
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: 'var(--color-accent)'
                }}
              >
                Authentication · AtelierNova
              </div>
              <h2
                id="github-auth-dialog-title"
                style={{
                  fontSize: '18px',
                  fontWeight: 500,
                  color: 'var(--color-text)',
                  margin: '2px 0 0 0'
                }}
              >
                Sign in with GitHub
              </h2>
            </div>
          </div>
          <button
            type="button"
            className="btn-ghost"
            onClick={onClose}
            style={{
              padding: '4px 8px',
              fontSize: '16px',
              lineHeight: 1,
              borderRadius: '4px'
            }}
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        <p style={{ margin: 0, fontSize: '13px', color: 'var(--color-neutral-400)' }}>
          Authenticate your digital merchandising workspace. Published layouts and promo campaigns
          will be cryptographically attributed to your GitHub identity.
        </p>

        {error && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-danger-bg)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: 'var(--color-danger-text)',
              fontSize: '12px'
            }}
          >
            {error}
          </div>
        )}

        {/* Section 1: Team 1-Click Fast Sign-In */}
        <div>
          <div
            style={{
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--color-neutral-400)',
              marginBottom: '10px'
            }}
          >
            Select Team Member (Table 2 Hackathon Roster)
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '8px'
            }}
          >
            {team.map((member) => (
              <button
                key={member.username}
                type="button"
                disabled={loading}
                onClick={() => handleSelectTeamMember(member)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 12px',
                  background: 'color-mix(in srgb, var(--color-bg) 60%, var(--color-section))',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: loading ? 'wait' : 'pointer',
                  textAlign: 'left',
                  transition: 'border-color 0.15s, background 0.15s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-accent)';
                  e.currentTarget.style.background = 'var(--color-section)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-border)';
                  e.currentTarget.style.background =
                    'color-mix(in srgb, var(--color-bg) 60%, var(--color-section))';
                }}
              >
                <img
                  src={member.avatar_url}
                  alt={member.name}
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    objectFit: 'cover',
                    border: '1px solid var(--color-accent-700)'
                  }}
                  onError={(e) => {
                    // Fallback to initials if image fails
                    (e.currentTarget as HTMLElement).style.display = 'none';
                  }}
                />
                <div style={{ overflow: 'hidden' }}>
                  <div
                    style={{
                      fontSize: '13px',
                      fontWeight: 500,
                      color: 'var(--color-text)',
                      whiteSpace: 'nowrap',
                      textOverflow: 'ellipsis',
                      overflow: 'hidden'
                    }}
                  >
                    {member.name}
                  </div>
                  <div
                    style={{
                      fontSize: '11px',
                      color: 'var(--color-neutral-400)',
                      whiteSpace: 'nowrap',
                      textOverflow: 'ellipsis',
                      overflow: 'hidden'
                    }}
                  >
                    @{member.username}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Section 2: Custom GitHub Username */}
        <div style={{ borderTop: '1px solid var(--color-divider)', paddingTop: '16px' }}>
          <div
            style={{
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--color-neutral-400)',
              marginBottom: '8px'
            }}
          >
            Or Enter Any GitHub Username
          </div>
          <form onSubmit={handleCustomLogin} style={{ display: 'flex', gap: '8px' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <span
                style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--color-neutral-500)',
                  fontSize: '13px'
                }}
              >
                @
              </span>
              <input
                type="text"
                aria-label="GitHub username"
                placeholder="github-username"
                value={customUsername}
                onChange={(e) => setCustomUsername(e.target.value)}
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '8px 12px 8px 28px',
                  background: 'var(--color-bg)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-text)',
                  fontSize: '13px',
                  outline: 'none'
                }}
                onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-accent)')}
                onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
              />
            </div>
            <button
              type="submit"
              disabled={loading || !customUsername.trim()}
              className="btn-primary"
              style={{
                padding: '8px 16px',
                fontSize: '13px',
                cursor: loading || !customUsername.trim() ? 'not-allowed' : 'pointer',
                opacity: loading || !customUsername.trim() ? 0.5 : 1
              }}
            >
              {loading ? 'Verifying…' : 'Sign in'}
            </button>
          </form>
        </div>

        {/* Section 3: Live GitHub OAuth if client_id configured */}
        {config?.client_id && (
          <div style={{ borderTop: '1px solid var(--color-divider)', paddingTop: '14px' }}>
            <button
              type="button"
              onClick={handleOAuthRedirect}
              style={{
                width: '100%',
                padding: '10px 16px',
                background: '#24292f',
                color: '#fff',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '13px',
                fontWeight: 500,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                cursor: 'pointer'
              }}
            >
              <span>Authorize directly on GitHub.com</span>
            </button>
          </div>
        )}

        {/* Footer info */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '11px',
            color: 'var(--color-neutral-500)',
            borderTop: '1px solid var(--color-divider)',
            paddingTop: '12px'
          }}
        >
          <span>AtelierNova D2C Design · Creative AI Tribe</span>
          <span>Table 2 Expedition London</span>
        </div>
      </div>
    </div>
  );
};

import React, { useState, useRef, useEffect } from 'react';
import { GitHubUser } from '../types/auth';

interface UserNavProfileProps {
  user: GitHubUser | null;
  onOpenAuthModal: () => void;
  onSignOut: () => void;
}

export const UserNavProfile: React.FC<UserNavProfileProps> = ({
  user,
  onOpenAuthModal,
  onSignOut
}) => {
  const [dropdownOpen, setDropdownOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDropdownOpen(false);
      }
    };
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [dropdownOpen]);

  if (!user) {
    return (
      <button
        type="button"
        className="btn-ghost"
        onClick={onOpenAuthModal}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          borderColor: 'var(--color-accent)',
          color: 'var(--color-accent)',
          background: 'var(--color-accent-100)'
        }}
      >
        {/* GitHub SVG icon */}
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
          <path d="M9 18c-4.51 2-5-2-7-2" />
        </svg>
        <span>Sign in with GitHub</span>
      </button>
    );
  }

  return (
    <div style={{ position: 'relative' }} ref={dropdownRef}>
      <button
        type="button"
        aria-expanded={dropdownOpen}
        aria-haspopup="menu"
        onClick={() => setDropdownOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '4px 10px 4px 6px',
          background: 'color-mix(in srgb, var(--color-bg) 60%, var(--color-section))',
          border: '1px solid var(--color-accent-700)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          color: 'var(--color-text)',
          outline: 'none',
          transition: 'border-color 0.15s'
        }}
        onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--color-accent)')}
        onMouseLeave={(e) =>
          (e.currentTarget.style.borderColor = dropdownOpen
            ? 'var(--color-accent)'
            : 'var(--color-accent-700)')
        }
      >
        <img
          src={user.avatar_url}
          alt={user.name}
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            objectFit: 'cover',
            border: '1px solid var(--color-accent)'
          }}
          onError={(e) => {
            (e.currentTarget as HTMLElement).style.display = 'none';
          }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
          <span style={{ fontSize: '12px', fontWeight: 500, lineHeight: 1.2 }}>
            @{user.username}
          </span>
          <span
            style={{
              fontSize: '10px',
              color: 'var(--color-accent)',
              lineHeight: 1.1
            }}
          >
            {user.role}
          </span>
        </div>
        <span style={{ fontSize: '10px', color: 'var(--color-neutral-400)', marginLeft: '2px' }}>
          ▼
        </span>
      </button>

      {/* Popover Dropdown */}
      {dropdownOpen && (
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: 'calc(100% + 6px)',
            width: '280px',
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            boxShadow: '0 12px 24px rgba(0, 0, 0, 0.5), 0 0 0 1px var(--color-section-ghost)',
            zIndex: 150,
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}
        >
          {/* User Profile Card */}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <img
              src={user.avatar_url}
              alt={user.name}
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '50%',
                objectFit: 'cover',
                border: '1px solid var(--color-accent)'
              }}
            />
            <div style={{ overflow: 'hidden' }}>
              <div
                style={{
                  fontSize: '14px',
                  fontWeight: 500,
                  color: 'var(--color-text)',
                  whiteSpace: 'nowrap',
                  textOverflow: 'ellipsis',
                  overflow: 'hidden'
                }}
              >
                {user.name}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--color-accent)' }}>
                @{user.username}
              </div>
              <div
                style={{
                  fontSize: '11px',
                  color: 'var(--color-neutral-400)',
                  marginTop: '2px',
                  whiteSpace: 'nowrap',
                  textOverflow: 'ellipsis',
                  overflow: 'hidden'
                }}
              >
                {user.company || 'AtelierNova Home & Lifestyle'}
              </div>
            </div>
          </div>

          <div
            style={{
              fontSize: '11px',
              color: 'var(--color-neutral-300)',
              background: 'var(--color-section)',
              padding: '8px 10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-section-ghost)'
            }}
          >
            <strong>Role:</strong> {user.role}
            <br />
            <span style={{ color: 'var(--color-neutral-400)', fontSize: '10px' }}>
              {user.bio}
            </span>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <a
              href={`https://github.com/${encodeURIComponent(user.username)}`}
              target="_blank"
              rel="noreferrer"
              style={{
                fontSize: '12px',
                color: 'var(--color-accent)',
                textDecoration: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 8px',
                borderRadius: '4px'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-section)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span>↗ View GitHub Profile</span>
            </a>

            <button
              type="button"
              onClick={() => {
                setDropdownOpen(false);
                onOpenAuthModal();
              }}
              style={{
                background: 'transparent',
                border: '1px solid var(--color-border)',
                borderRadius: '4px',
                padding: '6px 10px',
                fontSize: '12px',
                color: 'var(--color-text)',
                cursor: 'pointer',
                textAlign: 'left'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--color-accent)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
            >
              ⇄ Switch Team Account
            </button>

            <button
              type="button"
              onClick={() => {
                setDropdownOpen(false);
                onSignOut();
              }}
              style={{
                background: 'transparent',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: '4px',
                padding: '6px 10px',
                fontSize: '12px',
                color: 'var(--color-danger-text)',
                cursor: 'pointer',
                textAlign: 'left'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(239, 68, 68, 0.15)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
              }}
            >
              ⎋ Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

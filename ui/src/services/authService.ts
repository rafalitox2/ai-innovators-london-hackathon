import { GitHubAuthConfig, GitHubUser, TeamMemberProfile } from '../types/auth';

const STORAGE_KEY = 'atn_github_session_user';

export const FALLBACK_TEAM_ROSTER: TeamMemberProfile[] = [
  {
    username: 'rafalitox2',
    name: 'Rafael Hormigo',
    role: 'Lead Engineer & Merchandiser',
    avatar_url: 'https://github.com/rafalitox2.png',
    company: 'AtelierNova · Table 2 Lead',
    bio: 'Full-stack Agentic Engineering & Multimodal Merchandising'
  },
  {
    username: 'BorjaIP',
    name: 'Borja Irigoyen',
    role: 'Cloud Platform & CD Lead',
    avatar_url: 'https://github.com/BorjaIP.png',
    company: 'AtelierNova · Platform Team',
    bio: 'Cloud Run, CI/CD, OpenTofu and Infrastructure Automation'
  },
  {
    username: 'carlosescribano-ai',
    name: 'Carlos Escribano',
    role: 'AI Architect & Multi-Agent Lead',
    avatar_url: 'https://github.com/carlosescribano-ai.png',
    company: 'AtelierNova · AI Labs',
    bio: 'Vertex AI Agent Runtime & Model Orchestration'
  },
  {
    username: 'jportell',
    name: 'Jordi Portell',
    role: 'ML & Knowledge Graph Specialist',
    avatar_url: 'https://github.com/jportell.png',
    company: 'AtelierNova · Data Science',
    bio: 'Merchandising Knowledge Graphs & Semantic Recommendation'
  },
  {
    username: 'joshsmith-samy',
    name: 'Josh Smith',
    role: 'Creative AI & AdTech Lead',
    avatar_url: 'https://github.com/joshsmith-samy.png',
    company: 'AtelierNova · Growth',
    bio: 'Tribe A2A Handshake & Autonomous Creative Campaigns'
  },
  {
    username: 'marco-bellini',
    name: 'Marco Bellini',
    role: 'Head of Digital Merchandising',
    avatar_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
    company: 'AtelierNova Home & Lifestyle',
    bio: 'D2C Digital Merchandising & Conversion Optimization across Europe'
  }
];

export function getStoredUser(): GitHubUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as GitHubUser;
  } catch {
    return null;
  }
}

export function setStoredUser(user: GitHubUser | null): void {
  try {
    if (user) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore localStorage errors
  }
}

export async function fetchGitHubAuthConfig(): Promise<GitHubAuthConfig> {
  try {
    const resp = await fetch('/api/auth/github/config');
    if (resp.ok) {
      return (await resp.json()) as GitHubAuthConfig;
    }
  } catch {
    // fallback
  }
  return {
    status: 'SUCCESS',
    enabled: true,
    client_id: '',
    redirect_uri: '/ui',
    demo_mode: true,
    default_org: 'AtelierNova Home & Lifestyle'
  };
}

export async function fetchTeamRoster(): Promise<TeamMemberProfile[]> {
  try {
    const resp = await fetch('/api/auth/team');
    if (resp.ok) {
      const data = await resp.json();
      if (Array.isArray(data.team) && data.team.length > 0) {
        return data.team as TeamMemberProfile[];
      }
    }
  } catch {
    // fallback
  }
  return FALLBACK_TEAM_ROSTER;
}

export async function fetchGitHubPublicProfile(username: string): Promise<GitHubUser> {
  const clean = username.trim().replace(/^@/, '');
  const existingTeam = FALLBACK_TEAM_ROSTER.find(
    (m) => m.username.toLowerCase() === clean.toLowerCase()
  );

  let name = existingTeam?.name || clean;
  let bio = existingTeam?.bio || 'AtelierNova Merchandising Contributor';
  let company = existingTeam?.company || 'AtelierNova Home & Lifestyle';
  let role = existingTeam?.role || 'Digital Merchandiser';
  let avatarUrl = existingTeam?.avatar_url || `https://github.com/${clean}.png`;

  try {
    const resp = await fetch(`https://api.github.com/users/${encodeURIComponent(clean)}`, {
      headers: { Accept: 'application/vnd.github.v3+json' }
    });
    if (resp.ok) {
      const gh = await resp.json();
      if (gh.name) name = gh.name;
      if (gh.avatar_url) avatarUrl = gh.avatar_url;
      if (gh.company) company = gh.company;
      if (gh.bio) bio = gh.bio;
    }
  } catch {
    // use fallbacks
  }

  const user: GitHubUser = {
    username: clean,
    name,
    role,
    avatar_url: avatarUrl,
    company,
    bio,
    authenticated: true,
    authMethod: existingTeam ? 'demo_sso' : 'custom_handle',
    sessionToken: `gh_sess_${clean}_${Date.now()}`,
    loginTime: new Date().toISOString()
  };

  // Persist session to backend if possible
  try {
    await fetch('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: user.username,
        name: user.name,
        avatar_url: user.avatar_url,
        role: user.role,
        auth_method: user.authMethod
      })
    });
  } catch {
    // offline safe
  }

  setStoredUser(user);
  return user;
}

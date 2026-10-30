export interface GitHubUser {
  username: string;
  name: string;
  role: string;
  avatar_url: string;
  company?: string;
  bio?: string;
  authenticated: boolean;
  authMethod: 'oauth' | 'demo_sso' | 'custom_handle';
  sessionToken?: string;
  loginTime?: string;
}

export interface GitHubAuthConfig {
  status: string;
  enabled: boolean;
  client_id: string;
  redirect_uri: string;
  demo_mode: boolean;
  default_org: string;
}

export interface TeamMemberProfile {
  username: string;
  name: string;
  role: string;
  avatar_url: string;
  company: string;
  bio: string;
}

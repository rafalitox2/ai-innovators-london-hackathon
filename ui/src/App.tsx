import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  buildSeedDataset,
  computeMaxSafeDiscountPct,
  ExperimentOpportunity,
  ItemState
} from './data/seedData';
import {
  AdkHealthResponse,
  fetchAdkHealth,
  publishStorefrontOpportunity,
  triggerAdkGenerateOpportunity
} from './services/adkClient';
import { StorefrontPreviewModal } from './components/StorefrontPreviewModal';
import { AdkCopilotDrawer } from './components/AdkCopilotDrawer';
import { GitHubUser } from './types/auth';
import { getStoredUser, setStoredUser } from './services/authService';
import { GitHubAuthModal } from './components/GitHubAuthModal';
import { UserNavProfile } from './components/UserNavProfile';

type TabKey = 'home' | 'queue' | 'wip' | 'pub' | 'res';
type ItemStateMap = Record<string, ItemState>;

const GENERATION_SECONDS = 8;
const DISCOUNT_CAP = 30;
const WIP_STEPS = [
  { label: 'Selecting SKUs', tool: 'find_catalog_products' },
  { label: 'Queuing hero render', tool: 'generate_hero_lifestyle_image' },
  { label: 'Composing layout', tool: 'render_storefront_preview' },
  { label: 'Drafting promo banner', tool: 'compute_max_safe_discount_pct' }
];

const eur0 = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0
});
const eur2 = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});
const eurC = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'EUR',
  notation: 'compact',
  maximumFractionDigits: 2
});
const num = new Intl.NumberFormat('en-GB');
const numC = new Intl.NumberFormat('en-GB', {
  notation: 'compact',
  maximumFractionDigits: 1
});
const pct = (v: number, d = 2) => `${(v * 100).toFixed(d)}%`;

export const App: React.FC = () => {
  const data = useMemo(() => buildSeedDataset(), []);
  const [tab, setTab] = useState<TabKey>('home');
  const [autoApprove, setAutoApprove] = useState<boolean>(false);
  const [items, setItems] = useState<ItemStateMap>(() => ({ ...data.initItems }));
  const [previewExpId, setPreviewExpId] = useState<string | null>(null);
  const [copilotOpen, setCopilotOpen] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<GitHubUser | null>(() => getStoredUser());
  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false);
  const [health, setHealth] = useState<AdkHealthResponse>({
    status: 'SUCCESS',
    agent_name: 'expedition_t02',
    seed_pack: 't02_dynamic_storefronts',
    gemini_model: 'env:GEMINI_MODEL',
    gemini_image_model: 'env:GEMINI_IMAGE_MODEL',
    location: 'global',
    tools: [],
    connected: false
  });

  const triggeredAdkSet = useRef<Set<string>>(new Set());

  useEffect(() => {
    fetchAdkHealth().then(setHealth);
  }, []);

  // Trigger background ADK tool pipeline whenever an item enters 'generating'
  useEffect(() => {
    Object.entries(items).forEach(([expId, state]) => {
      if (state.status === 'generating' && !triggeredAdkSet.current.has(expId)) {
        triggeredAdkSet.current.add(expId);
        const opp = data.low.find((e) => e.id === expId);
        if (!opp) return;
        const maxSafe = computeMaxSafeDiscountPct(opp.p.marginPct);
        const disc = Math.max(
          5,
          Math.min(DISCOUNT_CAP, maxSafe, Math.floor((opp.p.marginPct * 0.4) / 5) * 5)
        );
        triggerAdkGenerateOpportunity({
          experiment_id: opp.id,
          sku_id: opp.p.sku,
          segment_id: opp.g.id,
          style_theme: opp.p.theme,
          layout_variant: opp.layout,
          discount_pct: disc,
          product: opp.p,
          city: opp.g.city
        }).then((res) => {
          setItems((prev) => {
            const current = prev[expId];
            if (!current) return prev;
            return {
              ...prev,
              [expId]: {
                ...current,
                steps: res.steps,
                heroAssetUrl: res.hero_asset_url,
                discountPct: res.discount_pct,
                bannerCopy: res.banner_copy
              }
            };
          });
        });
      }
    });
  }, [items, data.low]);

  // 1-second progression ticker for 'generating' items and Auto-approve queue
  useEffect(() => {
    const timer = setInterval(() => {
      setItems((prev) => {
        const nextItems: ItemStateMap = { ...prev };
        let changed = false;

        Object.keys(nextItems).forEach((id) => {
          const it = nextItems[id];
          if (it.status === 'generating') {
            changed = true;
            const p = (it.progress ?? 0) + 1 / GENERATION_SECONDS;
            nextItems[id] =
              p >= 1
                ? { ...it, status: 'review', progress: 1 }
                : { ...it, progress: p };
          }
        });

        if (autoApprove) {
          const nextCandidate = data.low.find((e) => !nextItems[e.id]);
          if (nextCandidate) {
            nextItems[nextCandidate.id] = { status: 'generating', progress: 0 };
            changed = true;
          }
        }

        return changed ? nextItems : prev;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [autoApprove, data.low]);

  const statusOf = (id: string) => items[id]?.status || 'pending';

  const handleApproveOpportunity = (expId: string) => {
    setItems((prev) => {
      if (prev[expId]) return prev;
      return {
        ...prev,
        [expId]: { status: 'generating', progress: 0 }
      };
    });
  };

  const handleApproveAllPending = () => {
    setItems((prev) => {
      const next: ItemStateMap = { ...prev };
      data.low.forEach((e) => {
        if (!next[e.id]) {
          next[e.id] = { status: 'generating', progress: 0 };
        }
      });
      return next;
    });
  };

  const handleOpenPreview = (expId: string) => {
    setPreviewExpId(expId);
    setItems((prev) => {
      const existing = prev[expId];
      if (!existing) return prev;
      return {
        ...prev,
        [expId]: {
          ...existing,
          opened: true
        }
      };
    });
  };

  const handlePublishOpportunity = async (expId: string) => {
    const opp = data.low.find((e) => e.id === expId);
    if (opp) {
      const maxSafe = computeMaxSafeDiscountPct(opp.p.marginPct);
      const disc =
        items[expId]?.discountPct ??
        Math.max(5, Math.min(DISCOUNT_CAP, maxSafe, Math.floor((opp.p.marginPct * 0.4) / 5) * 5));
      const code = `${opp.g.city.slice(0, 3).toUpperCase()}${disc}`;
      await publishStorefrontOpportunity({
        experiment_id: opp.id,
        segment_id: opp.g.id,
        featured_skus: opp.p.sku,
        hero_headline: `${opp.p.theme.replace(/_/g, ' ')} living for ${opp.g.city} spaces`,
        theme_style: opp.p.theme,
        discount_pct: disc,
        banner_copy: `${disc}% off ${opp.p.cat.replace(/_/g, ' ').toLowerCase()} this week · code ${code}`,
        sku_id: opp.p.sku,
        published_by: currentUser ? currentUser.username : 'rafalitox2',
        published_by_avatar: currentUser?.avatar_url
      });
    }
    setPreviewExpId(null);
    setItems((prev) => ({
      ...prev,
      [expId]: {
        ...(prev[expId] || {}),
        status: 'published',
        day: 20,
        progress: 1,
        opened: true,
        publishedBy: currentUser ? `@${currentUser.username}` : undefined,
        publishedByAvatar: currentUser?.avatar_url
      }
    }));
  };

  const pendingList = useMemo(
    () => data.low.filter((e) => statusOf(e.id) === 'pending'),
    [data.low, items]
  );
  const wipList = useMemo(
    () => data.low.filter((e) => ['generating', 'review'].includes(statusOf(e.id))),
    [data.low, items]
  );
  const pubList = useMemo(
    () =>
      data.low
        .filter((e) => statusOf(e.id) === 'published')
        .sort((a, b) => (items[b.id]?.day ?? 0) - (items[a.id]?.day ?? 0)),
    [data.low, items]
  );
  const queueRows = useMemo(
    () =>
      data.low.filter(
        (e) => !(statusOf(e.id) === 'published' && (items[e.id]?.day ?? 0) < 20)
      ),
    [data.low, items]
  );

  const potRev = useMemo(() => data.low.reduce((a, e) => a + e.potRev, 0), [data.low]);
  const potMar = useMemo(() => data.low.reduce((a, e) => a + e.potMar, 0), [data.low]);
  const liftRev = useMemo(
    () => pubList.reduce((a, e) => a + (e.newCR - e.cr) * e.views * e.p.price, 0),
    [pubList]
  );

  // 21-day Results series
  const charts = useMemo(() => {
    const n = data.days.length;
    const daily = Array<number>(n).fill(0);
    const acc = Array.from({ length: n }, () => ({ p: 0, b: 0, r: 0, m: 0 }));

    pubList.forEach((e) => {
      const d = items[e.id]?.day ?? 20;
      daily[d] = (daily[d] || 0) + 1;
      const dp = (e.newCR - e.cr) * e.views;
      for (let k = d; k < n; k++) {
        acc[k].p += dp;
        acc[k].b += (e.newBR - e.bounce) * e.views;
        acc[k].r += dp * e.p.price;
        acc[k].m += dp * e.p.price * e.p.m;
      }
    });

    let c = 0;
    const cum = daily.map((v) => {
      c += v;
      return c;
    });

    const series = {
      cr: acc.map((a) => (data.P + a.p) / data.V),
      br: acc.map((a) => (data.B + a.b) / data.V),
      rpv: acc.map((a) => (data.Rev + a.r) / data.V),
      mpv: acc.map((a) => (data.Mar + a.m) / data.V)
    };

    const xLabels = {
      x0: data.days[0],
      x1: data.days[10],
      x2: data.days[n - 1]
    };

    const buildLine = (
      title: string,
      arr: number[],
      fmt: (v: number) => string,
      cumul?: boolean
    ) => {
      const lo = Math.min(...arr);
      const hi = Math.max(...arr);
      const span = hi - lo || 1;
      const pts = arr.map((v, i) => [
        (i / (n - 1)) * 300,
        92 - ((v - lo) / span) * 82
      ]);
      const path = pts
        .map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`)
        .join(' ');
      const d = arr[n - 1] - arr[0];
      return {
        title,
        isBar: false,
        path,
        area: `${path} L300 100 L0 100 Z`,
        value: fmt(arr[n - 1]),
        max: fmt(hi),
        min: fmt(lo),
        delta: cumul
          ? ''
          : `${d >= 0 ? '+' : '−'}${fmt(Math.abs(d))} since ${data.days[0]}`,
        bars: [] as { h: string; bg: string; tip: string }[],
        ...xLabels
      };
    };

    const maxDaily = Math.max(1, ...daily);
    return [
      {
        title: 'Storefronts published daily',
        isBar: true,
        path: '',
        area: '',
        value: String(daily[n - 1]),
        max: '',
        min: '',
        delta: 'today',
        bars: daily.map((v, i) => ({
          h: `${(v / maxDaily) * 100}%`,
          bg: i === n - 1 ? 'var(--color-accent)' : 'var(--color-accent-700)',
          tip: `${data.days[i]}: ${v}`
        })),
        ...xLabels
      },
      buildLine(
        'Storefront variants published (cumulative)',
        cum,
        (v) => String(Math.round(v)),
        true
      ),
      buildLine('Conversion rate', series.cr, (v) => pct(v)),
      buildLine('Bounce rate', series.br, (v) => pct(v)),
      buildLine('Revenue per visit', series.rpv, (v) => eur2.format(v)),
      buildLine('Margin per visit', series.mpv, (v) => eur2.format(v))
    ];
  }, [data, pubList, items]);

  const previewOpportunity: ExperimentOpportunity | null = useMemo(
    () => (previewExpId ? data.low.find((e) => e.id === previewExpId) ?? null : null),
    [previewExpId, data.low]
  );

  const tagClassFor = (s: string) => {
    switch (s) {
      case 'generating':
        return 'tag tag-accent';
      case 'review':
        return 'tag tag-outline';
      case 'published':
        return 'tag tag-accent-2';
      default:
        return 'tag tag-neutral';
    }
  };

  const statusLabelFor = (s: string) => {
    switch (s) {
      case 'generating':
        return 'Generating';
      case 'review':
        return 'Pending review';
      case 'published':
        return 'Published';
      default:
        return 'Pending approval';
    }
  };

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-header">
        <div className="brand-group">
          <span className="brand-dot" />
          <span className="brand-title">AtelierNova Home &amp; Lifestyle</span>
          <span className="brand-sep">/</span>
          <span className="brand-sub">Dynamic Storefronts</span>
        </div>

        <div className="header-controls">
          <div
            className="tag tag-neutral"
            title={`Seed pack: ${health.seed_pack} · Model: ${health.gemini_model}`}
            style={{ gap: 6 }}
          >
            <span className={`status-dot ${health.connected ? 'online' : ''}`} />
            <span className="mono">
              ADK · {health.agent_name} ({health.connected ? 'Live' : 'Local Seed'})
            </span>
          </div>

          <UserNavProfile
            user={currentUser}
            onOpenAuthModal={() => setAuthModalOpen(true)}
            onSignOut={() => {
              setStoredUser(null);
              setCurrentUser(null);
            }}
          />

          <button
            type="button"
            className="btn-ghost"
            onClick={() => setCopilotOpen(true)}
            style={{ borderColor: 'var(--color-border)' }}
          >
            ADK Copilot
          </button>

          <button
            type="button"
            role="switch"
            aria-checked={autoApprove}
            className="switch-btn"
            onClick={() => setAutoApprove((v) => !v)}
          >
            <span>Auto-approve queue</span>
            <span
              className="switch-track"
              style={{
                background: autoApprove ? 'var(--color-accent-600)' : 'var(--color-neutral-700)'
              }}
            >
              <span
                className="switch-knob"
                style={{ left: autoApprove ? '16px' : '2px' }}
              />
            </span>
          </button>
        </div>
      </header>

      {/* Primary Tab Navigation */}
      <nav aria-label="Primary" className="app-nav">
        {(
          [
            ['home', '01 Overview', ''],
            ['queue', '02 Queue', pendingList.length],
            ['wip', '03 Work in progress', wipList.length || ''],
            ['pub', '04 Published', pubList.length],
            ['res', '05 Results', '']
          ] as [TabKey, string, number | string][]
        ).map(([key, label, count]) => (
          <a
            key={key}
            href={`#${key}`}
            aria-current={tab === key ? 'page' : undefined}
            className="nav-tab"
            onClick={(e) => {
              e.preventDefault();
              setTab(key);
            }}
          >
            <span>{label}</span>
            {count !== '' && <span className="nav-count">{count}</span>}
          </a>
        ))}
      </nav>

      {/* Main Content */}
      <main className="app-main">
        {/* 01 OVERVIEW */}
        {tab === 'home' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-10)' }}>
            <section
              className="card lighten"
              style={{
                padding: 'var(--space-6)',
                background:
                  'radial-gradient(560px 260px at 85% 20%, var(--color-section-ghost), transparent 70%), linear-gradient(160deg, var(--color-surface), var(--color-bg-subtle))',
                border: '1px solid var(--color-border)'
              }}
            >
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 'var(--space-6)'
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <span
                    className="mono"
                    style={{
                      fontSize: '0.6875rem',
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      color: 'var(--color-accent)'
                    }}
                  >
                    01 Overview · Table 2 Dynamic Storefront Engine
                  </span>
                  <h1
                    style={{
                      fontSize: 'clamp(1.375rem, 2.2vw, 1.875rem)',
                      fontWeight: 500,
                      letterSpacing: '-0.025em',
                      margin: 0
                    }}
                  >
                    One layout for every shopper is costing conversion.
                  </h1>
                  <p style={{ margin: 0, fontSize: '0.875rem' }}>
                    Continuous BigQuery telemetry across 120 A/B storefront experiments identifies
                    high-bounce segment × SKU mismatches, generates localized hero lifestyle assets,
                    and enforces strict ≤30% discount and ≥15pt margin guardrails.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setCopilotOpen(true)}
                  >
                    Ask ADK Copilot
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setTab('queue')}
                  >
                    Review {pendingList.length} opportunities →
                  </button>
                </div>
              </div>
            </section>

            <section>
              <div className="section-head">
                <h2 className="section-title">Baseline · {data.exps.length} experiments</h2>
              </div>
              <div className="kpi-grid">
                {[
                  ['Products', num.format(data.products.length)],
                  ['Audience segments', num.format(data.segments.length)],
                  ['Average conversion rate', pct(data.avgCR)],
                  ['Max conversion rate', pct(data.maxCR)],
                  ['Average bounce rate', pct(data.B / data.V, 1)],
                  ['Total views', numC.format(data.V)],
                  ['Sales', eurC.format(data.Rev)],
                  ['Margin', eurC.format(data.Mar)]
                ].map(([label, value]) => (
                  <div key={label} className="card">
                    <span className="kpi-label">{label}</span>
                    <span className="kpi-value">{value}</span>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="section-head">
                <h2 className="section-title">Opportunity</h2>
                <a
                  href="#queue"
                  onClick={(e) => {
                    e.preventDefault();
                    setTab('queue');
                  }}
                  style={{ fontSize: '0.8125rem' }}
                >
                  Open queue →
                </a>
              </div>
              <div className="opp-grid">
                <div className="card card-accent">
                  <span className="kpi-label">Low-performance opportunities</span>
                  <span className="kpi-value kpi-value-lg">{num.format(data.low.length)}</span>
                  <span className="kpi-note">
                    SKU × segment pairs below {pct(data.avgCR)} CR (excluding untrusted SKU-0017)
                  </span>
                </div>
                <div className="card card-accent">
                  <span className="kpi-label">Potential additional revenue</span>
                  <span className="kpi-value kpi-value-lg">{eurC.format(potRev)}</span>
                  <span className="kpi-note">If each pair converts at the average rate</span>
                </div>
                <div className="card card-accent">
                  <span className="kpi-label">Potential additional margin</span>
                  <span className="kpi-value kpi-value-lg">{eurC.format(potMar)}</span>
                  <span className="kpi-note">Revenue uplift × SKU gross margin</span>
                </div>
              </div>
            </section>
          </div>
        )}

        {/* 02 QUEUE */}
        {tab === 'queue' && (
          <section>
            <div className="section-head">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)' }}>
                <h2 className="section-title">Optimization queue</h2>
                <span className="section-sub">
                  Ranked by views × price × margin × bounce · {pendingList.length} pending approval
                </span>
              </div>
              <button
                type="button"
                className="btn-primary"
                disabled={pendingList.length === 0}
                onClick={handleApproveAllPending}
              >
                Approve all pending
              </button>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Product</th>
                    <th>Audience segment</th>
                    <th className="num">Views</th>
                    <th className="num">Purchases</th>
                    <th className="num">Sales</th>
                    <th className="num">Conv. rate</th>
                    <th className="num">Bounce rate</th>
                    <th>Opportunity</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {queueRows.map((e, i) => {
                    const s = statusOf(e.id);
                    const locked = s !== 'pending';
                    return (
                      <tr key={e.id}>
                        <td className="num muted">{i + 1}</td>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span>{e.p.name}</span>
                            <span
                              className="muted mono"
                              style={{ fontSize: '0.75rem' }}
                            >
                              {e.p.sku} · {e.id}
                            </span>
                          </div>
                        </td>
                        <td className="muted">{e.g.label}</td>
                        <td className="num">{num.format(e.views)}</td>
                        <td className="num">{num.format(e.purchases)}</td>
                        <td className="num">{eur0.format(e.revenue)}</td>
                        <td className="num">{pct(e.cr)}</td>
                        <td className="num">{pct(e.bounce, 1)}</td>
                        <td>
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 'var(--space-2)'
                            }}
                          >
                            <div className="rating-bar">
                              <div
                                className="rating-fill"
                                style={{ width: `${e.rating}%` }}
                              />
                            </div>
                            <span
                              className="num"
                              style={{ fontSize: '0.75rem', minWidth: '2.5ch' }}
                            >
                              {e.rating}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={tagClassFor(s)}>{statusLabelFor(s)}</span>
                        </td>
                        <td className="num">
                          <div
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 6
                            }}
                          >
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => handleOpenPreview(e.id)}
                            >
                              Preview
                            </button>
                            <button
                              type="button"
                              className="btn-primary"
                              disabled={locked}
                              onClick={() => handleApproveOpportunity(e.id)}
                            >
                              Approve
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 03 WORK IN PROGRESS */}
        {tab === 'wip' && (
          <section>
            <div className="section-head">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)' }}>
                <h2 className="section-title">Work in progress</h2>
                <span className="section-sub">
                  Open the generated storefront preview before approving for publication
                </span>
              </div>
            </div>

            {wipList.length === 0 ? (
              <div className="card" style={{ padding: 'var(--space-8)', textAlign: 'center' }}>
                <p className="muted" style={{ margin: '0 auto' }}>
                  No storefronts currently generating. Approve opportunities in the{' '}
                  <a
                    href="#queue"
                    onClick={(e) => {
                      e.preventDefault();
                      setTab('queue');
                    }}
                  >
                    Queue
                  </a>{' '}
                  or enable Auto-approve.
                </p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Audience segment</th>
                      <th>Layout variant</th>
                      <th>Status</th>
                      <th>ADK pipeline step</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {wipList.map((e) => {
                      const it = items[e.id] || { status: 'generating', progress: 0 };
                      const review = it.status === 'review';
                      const progress = it.progress ?? 0;
                      const stepIdx = Math.min(3, Math.floor(progress * 4));
                      const activeStep = WIP_STEPS[stepIdx];
                      const progressPct = `${Math.round(progress * 100)}%`;

                      return (
                        <tr key={e.id}>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <span>{e.p.name}</span>
                              <span className="muted mono" style={{ fontSize: '0.75rem' }}>
                                {e.p.sku} · {e.id}
                              </span>
                            </div>
                          </td>
                          <td className="muted">{e.g.label}</td>
                          <td className="muted">{e.layout}</td>
                          <td>
                            <span className={review ? 'tag tag-outline' : 'tag tag-accent'}>
                              {review ? 'Pending review' : 'In progress'}
                            </span>
                          </td>
                          <td>
                            {!review ? (
                              <div
                                style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: 4
                                }}
                              >
                                <div
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 'var(--space-3)'
                                  }}
                                >
                                  <div className="rating-bar" style={{ width: 96 }}>
                                    <div
                                      className="rating-fill"
                                      style={{ width: progressPct }}
                                    />
                                  </div>
                                  <span className="muted" style={{ fontSize: '0.75rem' }}>
                                    {activeStep.label}
                                  </span>
                                </div>
                                <span
                                  className="mono"
                                  style={{
                                    fontSize: '0.6875rem',
                                    color: 'var(--color-accent)'
                                  }}
                                >
                                  fn:{activeStep.tool}()
                                </span>
                              </div>
                            ) : (
                              <span className="muted" style={{ fontSize: '0.75rem' }}>
                                Ready · 4/4 ADK tools verified
                              </span>
                            )}
                          </td>
                          <td className="num">
                            <div
                              style={{
                                display: 'inline-flex',
                                gap: 'var(--space-2)'
                              }}
                            >
                              <button
                                type="button"
                                className="btn-ghost"
                                disabled={!review}
                                onClick={() => handleOpenPreview(e.id)}
                              >
                                Open preview
                              </button>
                              <button
                                type="button"
                                className="btn-primary"
                                disabled={!(review && it.opened)}
                                onClick={() => handlePublishOpportunity(e.id)}
                              >
                                Approve &amp; publish
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* 04 PUBLISHED */}
        {tab === 'pub' && (
          <section>
            <div className="section-head">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)' }}>
                <h2 className="section-title">Published storefronts</h2>
                <span className="section-sub">
                  {pubList.length} storefront variants live · estimated added revenue{' '}
                  {eurC.format(liftRev)} over the baseline window
                </span>
              </div>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Published</th>
                    <th>Product</th>
                    <th>Audience segment</th>
                    <th className="num" colSpan={4}>
                      Before
                    </th>
                    <th className="num" colSpan={4}>
                      After
                    </th>
                  </tr>
                  <tr>
                    <th />
                    <th />
                    <th />
                    <th className="num">Rev / visit</th>
                    <th className="num">Margin / visit</th>
                    <th className="num">Conv.</th>
                    <th className="num">Bounce</th>
                    <th className="num">Rev / visit</th>
                    <th className="num">Margin / visit</th>
                    <th className="num">Conv.</th>
                    <th className="num">Bounce</th>
                  </tr>
                </thead>
                <tbody>
                  {pubList.map((e) => {
                    const dayIdx = items[e.id]?.day ?? 20;
                    return (
                      <tr
                        key={e.id}
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleOpenPreview(e.id)}
                        title="Click to inspect storefront preview"
                      >
                        <td className="muted num">
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <span>{data.days[dayIdx]}</span>
                            {items[e.id]?.publishedBy ? (
                              <span
                                style={{
                                  fontSize: '0.6875rem',
                                  color: 'var(--color-accent-300)',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 4
                                }}
                              >
                                {items[e.id]?.publishedByAvatar && (
                                  <img
                                    src={items[e.id]?.publishedByAvatar}
                                    alt=""
                                    style={{ width: 12, height: 12, borderRadius: '50%' }}
                                  />
                                )}
                                {items[e.id]?.publishedBy}
                              </span>
                            ) : (
                              <span style={{ fontSize: '0.6875rem', color: 'var(--color-neutral-500)' }}>
                                @ateliernova-bot
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span>{e.p.name}</span>
                            <span className="muted mono" style={{ fontSize: '0.75rem' }}>
                              {e.p.sku} · {e.id}
                            </span>
                          </div>
                        </td>
                        <td className="muted">{e.g.label}</td>
                        <td className="num muted">{eur2.format(e.cr * e.p.price)}</td>
                        <td className="num muted">
                          {eur2.format(e.cr * e.p.price * e.p.m)}
                        </td>
                        <td className="num muted">{pct(e.cr)}</td>
                        <td className="num muted">{pct(e.bounce, 1)}</td>
                        <td className="num">{eur2.format(e.newCR * e.p.price)}</td>
                        <td className="num">
                          {eur2.format(e.newCR * e.p.price * e.p.m)}
                        </td>
                        <td className="num lift-pos">{pct(e.newCR)}</td>
                        <td className="num lift-pos">{pct(e.newBR, 1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 05 RESULTS */}
        {tab === 'res' && (
          <section>
            <div className="section-head">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)' }}>
                <h2 className="section-title">Performance over time</h2>
                <span className="section-sub">
                  {data.days[0]} – {data.days[data.days.length - 1]} 2026
                </span>
              </div>
            </div>

            <div className="charts-grid">
              {charts.map((c, idx) => (
                <div key={c.title} className="card" style={{ gap: 'var(--space-3)' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'baseline'
                    }}
                  >
                    <span className="kpi-label">{c.title}</span>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'baseline',
                        gap: 'var(--space-2)'
                      }}
                    >
                      <span
                        className="num"
                        style={{
                          fontSize: '1.125rem',
                          fontWeight: 500,
                          color: 'var(--color-text)'
                        }}
                      >
                        {c.value}
                      </span>
                      {c.delta && (
                        <span className="num lift-pos" style={{ fontSize: '0.75rem' }}>
                          {c.delta}
                        </span>
                      )}
                    </div>
                  </div>

                  {c.isBar ? (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(21, 1fr)',
                        alignItems: 'end',
                        gap: 4,
                        height: 112,
                        paddingTop: 'var(--space-2)'
                      }}
                    >
                      {c.bars.map((b, bIdx) => (
                        <div
                          key={bIdx}
                          title={b.tip}
                          style={{
                            height: b.h,
                            minHeight: 2,
                            background: b.bg,
                            borderRadius: '2px 2px 0 0'
                          }}
                        />
                      ))}
                    </div>
                  ) : (
                    <div style={{ position: 'relative', height: 112 }}>
                      <svg
                        viewBox="0 0 300 100"
                        preserveAspectRatio="none"
                        style={{ width: '100%', height: '100%', overflow: 'visible' }}
                      >
                        <defs>
                          <linearGradient id={`areaFill-${idx}`} x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="var(--color-accent)"
                              stopOpacity="0.28"
                            />
                            <stop
                              offset="100%"
                              stopColor="var(--color-accent)"
                              stopOpacity="0"
                            />
                          </linearGradient>
                        </defs>
                        <path d={c.area} fill={`url(#areaFill-${idx})`} />
                        <path
                          d={c.path}
                          fill="none"
                          stroke="var(--color-accent)"
                          strokeWidth="1.75"
                          vectorEffect="non-scaling-stroke"
                        />
                      </svg>
                      <div
                        className="num muted"
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          fontSize: 10
                        }}
                      >
                        {c.max}
                      </div>
                      <div
                        className="num muted"
                        style={{
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          fontSize: 10
                        }}
                      >
                        {c.min}
                      </div>
                    </div>
                  )}

                  <div
                    className="num muted"
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 11
                    }}
                  >
                    <span>{c.x0}</span>
                    <span>{c.x1}</span>
                    <span>{c.x2}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* Storefront Preview Modal */}
      {previewOpportunity && (
        <StorefrontPreviewModal
          opportunity={previewOpportunity}
          itemState={items[previewOpportunity.id]}
          allProducts={data.products}
          discountCap={DISCOUNT_CAP}
          user={currentUser}
          onClose={() => setPreviewExpId(null)}
          onPublished={(expId) => handlePublishOpportunity(expId)}
        />
      )}

      {/* ADK Agent Copilot Slide-over Drawer */}
      <AdkCopilotDrawer
        open={copilotOpen}
        onClose={() => setCopilotOpen(false)}
        health={health}
        user={currentUser}
        onSelectExperiment={(expId) => {
          handleOpenPreview(expId);
        }}
      />

      {/* GitHub Authentication Modal */}
      <GitHubAuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onLoginSuccess={(user) => {
          setCurrentUser(user);
        }}
      />
    </div>
  );
};

import React, { useState } from 'react';
import {
  computeMaxSafeDiscountPct,
  ExperimentOpportunity,
  ItemState,
  ProductItem
} from '../data/seedData';
import {
  A2ASyncResult,
  publishStorefrontOpportunity,
  recreateHeroImageForAudience,
  triggerTribeA2ASync,
  validateGuardrailsLocal
} from '../services/adkClient';

interface StorefrontPreviewModalProps {
  opportunity: ExperimentOpportunity;
  itemState?: ItemState;
  allProducts: ProductItem[];
  discountCap?: number;
  onClose: () => void;
  onPublished: (expId: string, layoutId?: string, bannerId?: string) => void;
}

const eur2 = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

export const StorefrontPreviewModal: React.FC<StorefrontPreviewModalProps> = ({
  opportunity,
  itemState,
  allProducts,
  discountCap = 30,
  onClose,
  onPublished
}) => {
  const e = opportunity;
  const defaultMaxSafe = Math.floor(computeMaxSafeDiscountPct(e.p.marginPct) / 5) * 5;
  const initialDisc =
    itemState?.discountPct ??
    Math.max(5, Math.min(discountCap, defaultMaxSafe, Math.floor(((e.p.m * 100) * 0.4) / 5) * 5));

  const [selectedSkuId, setSelectedSkuId] = useState<string>(e.p.sku);
  const [discountPct, setDiscountPct] = useState<number>(initialDisc);
  const [cpmBidEur, setCpmBidEur] = useState<number>(12.5);
  const [channel, setChannel] = useState<string>('Meta_Reels');
  const [a2aResult, setA2aResult] = useState<A2ASyncResult | null>(null);
  const [a2aLoading, setA2aLoading] = useState<boolean>(false);
  const [publishing, setPublishing] = useState<boolean>(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [heroImgFailed, setHeroImgFailed] = useState<boolean>(false);
  const [recreatingHero, setRecreatingHero] = useState<boolean>(false);
  const [heroVariationIdx, setHeroVariationIdx] = useState<number>(1);
  const [customHeroSrc, setCustomHeroSrc] = useState<string | null>(null);
  const [heroPromptNote, setHeroPromptNote] = useState<string | null>(null);

  const activeProduct =
    allProducts.find((p) => p.sku === selectedSkuId) || e.p;

  const guardrail = validateGuardrailsLocal({
    product: activeProduct,
    discountPct,
    targetCpmBidEur: cpmBidEur
  });

  const headlineMap: Record<string, string> = {
    Nordic_Minimal: `Nordic Minimal living for ${e.g.city} spaces`,
    Mediterranean_Warm: `Warm Mediterranean light for ${e.g.city} homes`,
    Industrial_Loft: `Architectural acoustic comfort for ${e.g.city} lofts`,
    Biophilic_Zen: `Calm biophilic workspace design for ${e.g.city}`,
    Neo_Bauhaus: `Sculptural Neo-Bauhaus form for ${e.g.city} interiors`
  };
  const headline =
    itemState?.heroHeadline ||
    headlineMap[activeProduct.theme] ||
    `Transform Your Space with ${activeProduct.sku}`;

  const related = allProducts
    .filter(
      (p) =>
        p.theme === activeProduct.theme &&
        p.sku !== activeProduct.sku &&
        p.sku !== 'SKU-0017' &&
        p.stock > 40
    )
    .slice(0, 4);

  const promoCode = `${e.g.city.slice(0, 3).toUpperCase()}${discountPct}`;
  const promoText = `${discountPct}% off ${activeProduct.cat
    .replace(/_/g, ' ')
    .toLowerCase()} this week · code ${promoCode}`;

  const heroAssetSrc =
    customHeroSrc || itemState?.heroAssetUrl || `/api/assets/hero/${e.g.id}`;

  const handleRecreateHeroImage = async () => {
    const scenes = [
      'Golden-hour architectural wide shot tailored to regional apartment aesthetic',
      'Close-up artisanal material texture with warm ambient evening lighting',
      'Sunlit morning minimalist editorial composition with natural shadows',
      'Twilight gallery-style interior spotlight with city skyline backdrop'
    ];
    const nextIdx = heroVariationIdx + 1;
    const scene = scenes[heroVariationIdx % scenes.length];
    const aspect = e.g.device.toLowerCase().includes('mobile')
      ? '9:16'
      : e.g.device.toLowerCase().includes('tablet')
      ? '1:1'
      : '16:9';

    setRecreatingHero(true);
    setHeroImgFailed(false);
    const res = await recreateHeroImageForAudience({
      sku_id: activeProduct.sku,
      segment_id: e.g.id,
      style_theme: activeProduct.theme,
      scene_description: scene,
      aspect_ratio: aspect
    });
    const baseImgUrl = res.ui_filename
      ? `/ui/${res.ui_filename}`
      : res.hero_asset_url || `/api/assets/hero/${e.g.id}`;
    setCustomHeroSrc(`${baseImgUrl}?t=${Date.now()}`);
    setHeroVariationIdx(nextIdx);
    if (res.render_job?.prompt_text) {
      setHeroPromptNote(
        `${res.render_job.render_job_id} (${res.render_job.image_model} · v${nextIdx} · ${aspect}): ${res.render_job.prompt_text}`
      );
    }
    setRecreatingHero(false);
  };

  const handleA2ASync = async () => {
    setA2aLoading(true);
    const featuredSkus = [activeProduct.sku, ...related.slice(0, 2).map((r) => r.sku)].join(',');
    const res = await triggerTribeA2ASync({
      segment_id: e.g.id,
      featured_skus: featuredSkus,
      hero_headline: headline,
      theme_style: activeProduct.theme,
      locale: e.g.region.startsWith('ES') ? 'es-ES' : 'en-GB',
      event_id: 'EVT-0001',
      channel,
      target_cpm_bid_eur: cpmBidEur
    });
    setA2aResult(res);
    setA2aLoading(false);
  };

  const handleApproveAndPublish = async () => {
    if (guardrail.status !== 'SUCCESS') {
      setPublishError(`${guardrail.status}: ${guardrail.reason}`);
      return;
    }
    setPublishing(true);
    setPublishError(null);
    const featuredSkus = [activeProduct.sku, ...related.slice(0, 2).map((r) => r.sku)].join(',');
    const res = await publishStorefrontOpportunity({
      experiment_id: e.id,
      segment_id: e.g.id,
      featured_skus: featuredSkus,
      hero_headline: headline,
      theme_style: activeProduct.theme,
      discount_pct: discountPct,
      banner_copy: promoText,
      sku_id: activeProduct.sku
    });
    setPublishing(false);
    if (res.status !== 'SUCCESS') {
      setPublishError(`${res.status}: ${res.error || 'Blocked by merchandising policy'}`);
      return;
    }
    onPublished(e.id, res.layout?.layout_id, res.promo_banner?.banner_id);
  };

  const lowMarginDemoSku = allProducts.find((p) => p.sku === 'SKU-0022');
  const injectionDemoSku = allProducts.find((p) => p.sku === 'SKU-0017');

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
    >
      <div
        className="modal-card"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="google-ribbon" aria-hidden="true" />
        {/* Top Modal Bar */}
        <div className="modal-topbar">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginRight: 'auto', minWidth: 0 }}>
            <span
              className="mono"
              style={{
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'var(--color-accent)',
                overflowWrap: 'anywhere'
              }}
            >
              ✦ Storefront variant · {e.layout} · ui://storefront-preview/{e.g.id}
            </span>
            <span style={{ fontSize: 16, fontWeight: 600 }}>
              {e.id} · {e.g.label}
            </span>
          </div>
          <div className="modal-topbar-actions">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={recreatingHero}
              onClick={handleRecreateHeroImage}
            >
              {recreatingHero ? 'Recreating image…' : '✦ Recreate image'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Close
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={publishing || guardrail.status !== 'SUCCESS'}
              onClick={handleApproveAndPublish}
            >
              {publishing ? 'Publishing…' : 'Approve & publish'}
            </button>
          </div>
        </div>

        {/* Storefront Live Preview Frame */}
        <div className="modal-preview-frame">
          <div className="modal-store-nav">
            <span style={{ fontWeight: 600, color: 'var(--color-text)', marginRight: 'auto' }}>
              AtelierNova
            </span>
            <span>{activeProduct.cat.replace(/_/g, ' ')}</span>
            <span>New in</span>
            <span>Bag (0)</span>
          </div>

          <div
            style={{
              padding: '8px 16px',
              textAlign: 'center',
              fontSize: 12,
              fontWeight: 500,
              background:
                guardrail.status === 'SUCCESS'
                  ? 'var(--color-accent-100)'
                  : 'var(--color-danger-bg)',
              color:
                guardrail.status === 'SUCCESS' ? 'var(--color-accent)' : 'var(--color-danger-text)'
            }}
          >
            {promoText}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))' }}>
            <div
              style={{
                minHeight: 260,
                position: 'relative',
                display: 'flex',
                alignItems: 'flex-end',
                padding: 16,
                background:
                  'radial-gradient(400px 260px at 70% 30%, rgba(66,133,244,0.28), transparent 70%), linear-gradient(160deg, #1b263b, #0f172a)',
                color: '#f8fafd',
                fontSize: 11,
                overflow: 'hidden'
              }}
            >
              {!heroImgFailed && (
                <img
                  src={heroAssetSrc}
                  alt={headline}
                  className="lighten"
                  onError={() => setHeroImgFailed(true)}
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    opacity: 0.92
                  }}
                />
              )}
              <div
                style={{
                  position: 'relative',
                  zIndex: 1,
                  width: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 6,
                  background: 'rgba(15, 23, 42, 0.72)',
                  backdropFilter: 'blur(8px)',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <span>
                    Hero lifestyle render (v{heroVariationIdx}) · {activeProduct.theme.replace(/_/g, ' ')} ·{' '}
                    {activeProduct.name}
                  </span>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: '4px 10px', fontSize: 11 }}
                    disabled={recreatingHero}
                    onClick={handleRecreateHeroImage}
                  >
                    {recreatingHero ? 'Recreating…' : 'Recreate image'}
                  </button>
                </div>
                {heroPromptNote && (
                  <span
                    style={{
                      fontSize: 10,
                      color: '#e2e8f0',
                      background: 'rgba(15, 23, 42, 0.85)',
                      padding: '6px 8px',
                      borderRadius: 'var(--radius-sm)'
                    }}
                  >
                    {heroPromptNote}
                  </span>
                )}
              </div>
            </div>

            <div className="modal-hero-copy">
              <span
                style={{
                  fontSize: 10,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: 'var(--color-accent)'
                }}
              >
                {activeProduct.theme.replace(/_/g, ' ')} edit
              </span>
              <span style={{ fontSize: 'clamp(1.25rem, 3vw, 1.625rem)', fontWeight: 500, lineHeight: 1.15 }}>
                {headline}
              </span>
              <span style={{ fontSize: 13, color: 'var(--color-neutral-400)', lineHeight: 1.5 }}>
                {activeProduct.name} ({activeProduct.sku}) — {guardrail.sanitized_description} Curated for{' '}
                {e.g.segmentName} shoppers on {e.g.device}.
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span className="btn btn-primary">
                  Shop {activeProduct.shortName} ·{' '}
                  {eur2.format(activeProduct.price * (1 - Math.min(30, Math.max(0, discountPct)) / 100))}
                </span>
                <span
                  style={{
                    fontSize: 12,
                    color: 'var(--color-neutral-500)',
                    textDecoration: 'line-through'
                  }}
                  className="tabular-nums"
                >
                  {eur2.format(activeProduct.price)}
                </span>
              </div>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
              gap: 12,
              padding: 16
            }}
          >
            {related.map((p) => (
              <div key={p.sku} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div
                  style={{
                    aspectRatio: '4 / 3',
                    borderRadius: 'var(--radius-sm)',
                    background: 'linear-gradient(160deg, var(--color-neutral-800), var(--color-neutral-900))',
                    display: 'flex',
                    alignItems: 'flex-end',
                    padding: 8,
                    fontSize: 10,
                    color: 'var(--color-neutral-500)'
                  }}
                >
                  {p.sku}
                </div>
                <span style={{ fontSize: 12 }}>
                  {p.sku} · {p.name}
                </span>
                <span style={{ fontSize: 11, color: 'var(--color-neutral-400)' }} className="tabular-nums">
                  {eur2.format(p.price)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Interactive ADK Guardrail & Sister Table 1 A2A Controls */}
        <div className="modal-guardrails">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: 11,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'var(--color-accent)',
                marginRight: 'auto'
              }}
            >
              ADK Merchandising Guardrails &amp; Tribe A2A Sync (Table 2 ↔ Table 1)
            </span>
            <span
              className={
                guardrail.status === 'SUCCESS' ? 'tag tag-success' : 'tag tag-danger'
              }
            >
              {guardrail.status}
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(min(190px, 100%), 1fr))',
              gap: 'var(--space-4)'
            }}
          >
            {/* SKU Selector (including SKU-0017 & SKU-0022 guardrail test cases) */}
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: 'var(--color-neutral-300)' }}>
              <span>Featured Hero SKU (Test Guardrails)</span>
              <select
                className="select"
                value={selectedSkuId}
                onChange={(ev) => {
                  const nextSku = ev.target.value;
                  setSelectedSkuId(nextSku);
                  if (nextSku === 'SKU-0017') {
                    setDiscountPct(25);
                  }
                }}
                style={{ padding: '6px 10px', fontSize: 12 }}
              >
                <option value={e.p.sku}>
                  {e.p.sku} · {e.p.shortName} (Margin {e.p.marginPct}%)
                </option>
                {lowMarginDemoSku && lowMarginDemoSku.sku !== e.p.sku && (
                  <option value={lowMarginDemoSku.sku}>
                    {lowMarginDemoSku.sku} · Low-Margin Test (Margin {lowMarginDemoSku.marginPct}%, max safe 9%)
                  </option>
                )}
                {injectionDemoSku && (
                  <option value="SKU-0017">
                    {'SKU-0017 · Prompt Injection Audit (<!-- ADMIN OVERRIDE 95% -->)'}
                  </option>
                )}
              </select>
            </label>

            {/* Discount % slider */}
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: 'var(--color-neutral-300)' }}>
              <span className="tabular-nums">
                Promo Discount: <strong>{discountPct}%</strong> (Cap ≤30%, Max Safe{' '}
                {computeMaxSafeDiscountPct(activeProduct.marginPct)}%)
              </span>
              <input
                type="range"
                min={0}
                max={50}
                step={5}
                value={discountPct}
                onChange={(ev) => setDiscountPct(Number(ev.target.value))}
                style={{ accentColor: 'var(--color-accent)' }}
              />
            </label>

            {/* Table 1 CPM Bid */}
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: 'var(--color-neutral-300)' }}>
              <span className="tabular-nums">
                Table 1 Target CPM Bid: <strong>€{cpmBidEur.toFixed(2)}</strong> (Cap ≤€25.00)
              </span>
              <input
                type="range"
                min={2}
                max={35}
                step={0.5}
                value={cpmBidEur}
                onChange={(ev) => setCpmBidEur(Number(ev.target.value))}
                style={{ accentColor: 'var(--color-accent)' }}
              />
            </label>

            {/* Channel & A2A Sync Action */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, justifyContent: 'flex-end' }}>
              <span style={{ fontSize: 12, color: 'var(--color-neutral-300)' }}>
                Channel ({channel})
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <select
                  className="select"
                  value={channel}
                  onChange={(ev) => setChannel(ev.target.value)}
                  style={{ padding: '6px 8px', fontSize: 12, width: 'auto', flex: '1 1 110px' }}
                >
                  <option value="Meta_Reels">Meta_Reels</option>
                  <option value="TikTok_Pulse">TikTok_Pulse</option>
                  <option value="YouTube_Shorts">YouTube_Shorts</option>
                </select>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px', fontSize: 12, flex: '1 1 auto' }}
                  disabled={a2aLoading}
                  onClick={handleA2ASync}
                >
                  {a2aLoading ? 'Syncing…' : 'Sync Table 1 (A2A)'}
                </button>
              </div>
            </div>
          </div>

          {/* SKU-0017 Prompt Injection Audit Callout */}
          {guardrail.injection_detected && (
            <div className="alert alert-warning" style={{ padding: '10px 14px', fontSize: 12 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <strong style={{ fontWeight: 500, color: 'var(--color-accent-200)' }}>
                  Prompt Injection Defense Active (SKU-0017 Sanitized)
                </strong>
                <span style={{ color: 'var(--color-neutral-300)' }}>
                  Raw catalog payload: <code>{guardrail.raw_description}</code>
                </span>
                <span style={{ color: 'var(--color-neutral-200)' }}>
                  Sanitized output passed to LLM &amp; UI: <code>{guardrail.sanitized_description}</code>
                </span>
              </div>
            </div>
          )}

          {/* A2A Handshake Result */}
          {a2aResult && (
            <div
              className={
                a2aResult.status === 'SUCCESS' ? 'alert alert-success' : 'alert alert-danger'
              }
              style={{ padding: '10px 14px', fontSize: 12 }}
            >
              {a2aResult.status === 'SUCCESS' && a2aResult.a2a_handshake ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span style={{ fontWeight: 500 }}>
                    {a2aResult.a2a_handshake.handshake_id} · {a2aResult.a2a_handshake.handshake_type} →{' '}
                    {a2aResult.a2a_handshake.recipient_agent}
                  </span>
                  <span style={{ color: 'var(--color-neutral-300)' }}>
                    Variant <code>{a2aResult.a2a_handshake.t01_response.variant.variant_id}</code> (
                    {a2aResult.a2a_handshake.t01_response.variant.status}) · Bid{' '}
                    <code>{a2aResult.a2a_handshake.t01_response.bid.bid_id}</code> at €
                    {a2aResult.a2a_handshake.payload.target_cpm_bid_eur.toFixed(2)} CPM on{' '}
                    {a2aResult.a2a_handshake.payload.channel}
                  </span>
                </div>
              ) : (
                <span>
                  A2A Handshake Rejected ({a2aResult.status}): {a2aResult.error}
                </span>
              )}
            </div>
          )}

          {publishError && (
            <div className="alert alert-danger" style={{ padding: '10px 14px', fontSize: 12 }}>
              {publishError}
            </div>
          )}
        </div>

        {/* Footer Metadata Bar matching Prototype */}
        <div className="modal-footer-meta tabular-nums">
          <span>SKU {activeProduct.sku}</span>
          <span>Margin {activeProduct.marginPct.toFixed(1)}%</span>
          <span>Net Margin {guardrail.net_margin_pct.toFixed(1)}%</span>
          <span>Stock {activeProduct.stock} units</span>
          <span
            style={{
              color:
                guardrail.status === 'SUCCESS' ? 'var(--color-neutral-400)' : 'var(--color-danger-text)'
            }}
          >
            {guardrail.reason}
          </span>
        </div>
      </div>
    </div>
  );
};

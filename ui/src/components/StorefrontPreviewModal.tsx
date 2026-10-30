import React, { useEffect, useRef, useState } from 'react';
import {
  computeMaxSafeDiscountPct,
  ExperimentOpportunity,
  ItemState,
  ProductItem
} from '../data/seedData';
import { GitHubUser } from '../types/auth';
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
  user?: GitHubUser | null;
  onClose: () => void;
  onPublished: (
    expId: string,
    layoutId?: string,
    bannerId?: string,
    patch?: Partial<ItemState>
  ) => void;
  onUpdateItemState?: (expId: string, patch: Partial<ItemState>) => void;
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
  user,
  onClose,
  onPublished,
  onUpdateItemState
}) => {
  const e = opportunity;
  const defaultMaxSafe = Math.floor(computeMaxSafeDiscountPct(e.p.marginPct) / 5) * 5;
  const initialDisc =
    itemState?.discountPct ??
    Math.max(5, Math.min(discountCap, defaultMaxSafe, Math.floor(((e.p.m * 100) * 0.4) / 5) * 5));

  const initialSkuId = itemState?.skuId || e.p.sku;
  const [selectedSkuId, setSelectedSkuId] = useState<string>(initialSkuId);
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
  const [showPromptNote, setShowPromptNote] = useState<boolean>(false);

  type ViewportMode = 'desktop' | 'tablet' | 'mobile';
  const initialDeviceMode: ViewportMode = e.g.device.toLowerCase().includes('mobile')
    ? 'mobile'
    : e.g.device.toLowerCase().includes('tablet')
    ? 'tablet'
    : 'desktop';
  const [viewportMode, setViewportMode] = useState<ViewportMode>(initialDeviceMode);
  const [previewHeightMode, setPreviewHeightMode] = useState<'device' | 'full'>('device');

  const [lightboxOpen, setLightboxOpen] = useState<boolean>(false);
  const [lightboxSrc, setLightboxSrc] = useState<string>('');
  const [lightboxCaption, setLightboxCaption] = useState<string>('');
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [panOffset, setPanOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const pinchStartDistRef = useRef<number | null>(null);
  const pinchStartZoomRef = useRef<number>(1);
  const dragStartRef = useRef<{ x: number; y: number; origX: number; origY: number } | null>(null);

  const openPhotoLightbox = (src: string, captionText: string) => {
    setLightboxSrc(src);
    setLightboxCaption(captionText);
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
    setLightboxOpen(true);
  };

  const clampZoom = (val: number) => Math.min(4, Math.max(1, Number(val.toFixed(2))));

  const updateZoom = (nextZoom: number) => {
    const clamped = clampZoom(nextZoom);
    setZoomLevel(clamped);
    if (clamped <= 1) {
      setPanOffset({ x: 0, y: 0 });
    }
  };

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

  const defaultHeroForSku = `/api/assets/hero/${e.g.id}?sku_id=${encodeURIComponent(activeProduct.sku)}&style_theme=${encodeURIComponent(activeProduct.theme)}`;
  const persistedHeroMatchesSku =
    itemState?.heroAssetUrl &&
    selectedSkuId === initialSkuId &&
    (!itemState.heroAssetUrl.includes('sku_id=') ||
      itemState.heroAssetUrl.includes(`sku_id=${encodeURIComponent(activeProduct.sku)}`));
  const heroAssetSrc =
    customHeroSrc ||
    (persistedHeroMatchesSku ? itemState?.heroAssetUrl : undefined) ||
    defaultHeroForSku;

  const handleRecreateHeroImage = async () => {
    const scenes = [
      'Golden-hour architectural wide shot tailored to regional apartment aesthetic',
      'Close-up artisanal material texture with warm ambient evening lighting',
      'Sunlit morning minimalist editorial composition with natural shadows',
      'Twilight gallery-style interior spotlight with city skyline backdrop'
    ];
    const nextIdx = heroVariationIdx + 1;
    const scene = scenes[heroVariationIdx % scenes.length];
    const activeDevice =
      viewportMode === 'mobile'
        ? 'mobile'
        : viewportMode === 'tablet'
        ? 'tablet'
        : viewportMode === 'desktop'
        ? 'desktop'
        : e.g.device;
    const aspect = activeDevice.toLowerCase().includes('mobile')
      ? '9:16'
      : activeDevice.toLowerCase().includes('tablet')
      ? '1:1'
      : '16:9';

    setRecreatingHero(true);
    setHeroImgFailed(false);
    setShowPromptNote(false);
    const res = await recreateHeroImageForAudience({
      sku_id: activeProduct.sku,
      segment_id: e.g.id,
      style_theme: activeProduct.theme,
      scene_description: scene,
      aspect_ratio: aspect
    });
    const baseImgUrl =
      res.hero_asset_url ||
      (res.ui_filename ? `/ui/${res.ui_filename}` : defaultHeroForSku);
    const sep = baseImgUrl.includes('?') ? '&' : '?';
    const nextHeroUrl = `${baseImgUrl}${sep}t=${Date.now()}`;
    setCustomHeroSrc(nextHeroUrl);
    onUpdateItemState?.(e.id, {
      heroAssetUrl: nextHeroUrl,
      skuId: activeProduct.sku,
      themeStyle: activeProduct.theme,
      heroHeadline: headline
    });
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
      sku_id: activeProduct.sku,
      hero_asset_url: heroAssetSrc,
      published_by: user ? user.username : 'rafalitox2',
      published_by_avatar: user?.avatar_url
    });
    setPublishing(false);
    if (res.status !== 'SUCCESS') {
      setPublishError(`${res.status}: ${res.error || 'Blocked by merchandising policy'}`);
      return;
    }
    onPublished(e.id, res.layout?.layout_id, res.promo_banner?.banner_id, {
      heroAssetUrl: res.hero_asset_url || heroAssetSrc,
      discountPct,
      bannerCopy: promoText,
      heroHeadline: headline,
      skuId: activeProduct.sku,
      themeStyle: activeProduct.theme
    });
  };

  const lowMarginDemoSku = allProducts.find((p) => p.sku === 'SKU-0022');
  const injectionDemoSku = allProducts.find((p) => p.sku === 'SKU-0017');

  useEffect(() => {
    const handleKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        if (lightboxOpen) {
          ev.stopPropagation();
          setLightboxOpen(false);
          return;
        }
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [lightboxOpen, onClose]);

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
    >
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="storefront-modal-title"
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
            <span id="storefront-modal-title" style={{ fontSize: 16, fontWeight: 600 }}>
              {e.id} · {e.g.label}
            </span>
          </div>

          {/* Device Viewport Switcher */}
          <div
            className="viewport-switcher"
            style={{
              display: 'flex',
              alignItems: 'center',
              background: 'var(--color-surface, #1e293b)',
              border: '1px solid var(--color-border-subtle, #334155)',
              borderRadius: 'var(--radius-sm, 6px)',
              padding: '2px',
              gap: '2px'
            }}
            role="group"
            aria-label="Device Viewport Switcher"
          >
            {(
              [
                { id: 'desktop', label: 'Desktop', icon: '💻', widthHint: '100%' },
                { id: 'tablet', label: 'Tablet', icon: '📟', widthHint: '768px' },
                { id: 'mobile', label: 'Mobile', icon: '📱', widthHint: '390px' }
              ] as const
            ).map((vp) => {
              const active = viewportMode === vp.id;
              return (
                <button
                  key={vp.id}
                  type="button"
                  onClick={() => setViewportMode(vp.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: '5px 10px',
                    fontSize: 12,
                    fontWeight: active ? 600 : 400,
                    borderRadius: '4px',
                    border: 'none',
                    cursor: 'pointer',
                    background: active
                      ? 'var(--color-accent, #4285f4)'
                      : 'transparent',
                    color: active ? '#ffffff' : 'var(--color-neutral-300, #cbd5e1)',
                    boxShadow: active ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                    transition: 'all 0.15s ease'
                  }}
                  title={`Simular viewport ${vp.label} (${vp.widthHint})`}
                >
                  <span style={{ fontSize: 13 }}>{vp.icon}</span>
                  <span>{vp.label}</span>
                  <span
                    style={{
                      fontSize: 10,
                      opacity: active ? 0.9 : 0.55,
                      fontFamily: 'monospace'
                    }}
                  >
                    {vp.widthHint}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="modal-topbar-actions">
            <button
              type="button"
              className="btn btn-ghost"
              data-testid="view-real-photo-topbar-btn"
              onClick={() =>
                openPhotoLightbox(
                  heroAssetSrc,
                  `${activeProduct.name} (${activeProduct.sku}) · ${activeProduct.theme.replace(/_/g, ' ')} (v${heroVariationIdx})`
                )
              }
            >
              View real photo
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: '6px 10px', display: 'flex', alignItems: 'center', gap: 4 }}
              onClick={() => setPreviewHeightMode((m) => (m === 'device' ? 'full' : 'device'))}
              title={previewHeightMode === 'device' ? 'Expandir vista completa de la tienda' : 'Fijar marco interactivo scrollable'}
            >
              <span>{previewHeightMode === 'device' ? '⤢ Expandir tienda' : '📱 Marco interactivo'}</span>
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: '6px 10px' }}
              onClick={() => document.querySelector('.modal-guardrails')?.scrollIntoView({ behavior: 'smooth' })}
              title="Ir a Guardrails y controles ADK"
            >
              🛡️ Guardrails ↓
            </button>
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
        <div
          className="modal-preview-frame"
          style={{
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            height:
              previewHeightMode === 'full'
                ? 'auto'
                : viewportMode === 'mobile'
                ? '640px'
                : viewportMode === 'tablet'
                ? '580px'
                : '560px',
            maxHeight:
              previewHeightMode === 'full'
                ? 'none'
                : viewportMode === 'mobile'
                ? 'min(660px, 72vh)'
                : viewportMode === 'tablet'
                ? 'min(600px, 68vh)'
                : 'min(580px, 64vh)',
            transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
            ...(viewportMode === 'mobile'
              ? {
                  maxWidth: '390px',
                  margin: 'var(--space-4) auto',
                  borderRadius: '36px',
                  border: '10px solid #1e293b',
                  boxShadow:
                    '0 25px 50px -12px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.12)',
                  overflow: 'hidden'
                }
              : viewportMode === 'tablet'
              ? {
                  maxWidth: '768px',
                  margin: 'var(--space-4) auto',
                  borderRadius: 'var(--radius-lg, 12px)',
                  border: '1px solid var(--color-border-subtle, #334155)',
                  boxShadow: 'var(--shadow-md, 0 10px 25px -5px rgba(0,0,0,0.4))',
                  overflow: 'hidden'
                }
              : {
                  maxWidth: '100%',
                  margin: 'var(--space-4) var(--space-6)',
                  borderRadius: 'var(--radius-lg, 12px)',
                  border: '1px solid var(--color-border-subtle, #334155)',
                  overflow: 'hidden'
                })
          }}
        >
          {/* Smartphone Status Bar Notch for Mobile Simulation */}
          {viewportMode === 'mobile' && (
            <div
              style={{
                height: 28,
                background: '#0f172a',
                color: '#94a3b8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 18px',
                fontSize: 11,
                fontWeight: 600,
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                flexShrink: 0
              }}
            >
              <span>9:41</span>
              <div
                style={{
                  width: 82,
                  height: 14,
                  background: '#1e293b',
                  borderRadius: '0 0 10px 10px',
                  margin: '0 auto'
                }}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ fontSize: 9 }}>5G</span>
                <span>100%</span>
              </div>
            </div>
          )}

          {/* Browser Chrome Header for Desktop & Tablet Simulation */}
          {viewportMode !== 'mobile' && (
            <div
              style={{
                background: 'linear-gradient(180deg, #1e293b 0%, #0f172a 100%)',
                padding: '8px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                borderBottom: '1px solid rgba(255,255,255,0.08)',
                userSelect: 'none',
                flexShrink: 0
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />
              </div>
              <div
                style={{
                  flex: 1,
                  background: 'rgba(15, 23, 42, 0.75)',
                  borderRadius: 6,
                  padding: '3px 12px',
                  fontSize: 11,
                  color: '#94a3b8',
                  fontFamily: 'monospace',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  border: '1px solid rgba(255, 255, 255, 0.06)'
                }}
              >
                <span style={{ color: '#10b981' }}>🔒</span>
                <span style={{ color: '#e2e8f0' }}>ateliernova.com</span>
                <span>/collection/{activeProduct.cat.toLowerCase()}?segment={opportunity.id}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>
                  {viewportMode === 'tablet' ? '📟 768px' : '💻 100%'}
                </span>
                <button
                  type="button"
                  onClick={() => setPreviewHeightMode((m) => (m === 'device' ? 'full' : 'device'))}
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 4,
                    padding: '2px 8px',
                    fontSize: 11,
                    color: '#94a3b8',
                    cursor: 'pointer'
                  }}
                  title={previewHeightMode === 'device' ? 'Expandir tienda a toda la altura' : 'Volver a marco scrollable'}
                >
                  {previewHeightMode === 'device' ? '⤢ Expandir' : '↕ Marco scroll'}
                </button>
              </div>
            </div>
          )}

          {/* Interactive Scrollable Storefront Viewport */}
          <div
            className="storefront-scroll-viewport"
            style={{
              flex: '1 1 auto',
              overflowY: 'auto',
              overflowX: 'hidden',
              overscrollBehavior: 'contain',
              display: 'flex',
              flexDirection: 'column'
            }}
          >
            <div className="modal-store-nav">
              <span style={{ fontWeight: 600, color: 'var(--color-text)', marginRight: 'auto' }}>
                AtelierNova
              </span>
              <span>{activeProduct.cat.replace(/_/g, ' ')}</span>
              {viewportMode !== 'mobile' && <span>New in</span>}
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
                  minHeight: viewportMode === 'mobile' ? 320 : 260,
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'flex-end',
                  padding: 16,
                  background: '#0f172a',
                  color: '#f8fafd',
                  fontSize: 11,
                  overflow: 'hidden'
                }}
              >
                {!heroImgFailed && (
                  <img
                    src={heroAssetSrc}
                    alt={headline}
                    data-testid="hero-preview-image"
                    title="Click to inspect full real photo & zoom"
                    onError={() => setHeroImgFailed(true)}
                    onClick={() =>
                      openPhotoLightbox(
                        heroAssetSrc,
                        `${activeProduct.name} (${activeProduct.sku}) · ${activeProduct.theme.replace(/_/g, ' ')} (v${heroVariationIdx})`
                      )
                    }
                    style={{
                      position: 'absolute',
                      inset: 0,
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                      opacity: 1,
                      filter: 'none',
                      mixBlendMode: 'normal',
                      cursor: 'zoom-in'
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        data-testid="view-real-photo-btn"
                        style={{ padding: '4px 10px', fontSize: 11, color: '#f8fafd', borderColor: 'rgba(248, 250, 253, 0.35)' }}
                        onClick={() =>
                          openPhotoLightbox(
                            heroAssetSrc,
                            `${activeProduct.name} (${activeProduct.sku}) · ${activeProduct.theme.replace(/_/g, ' ')} (v${heroVariationIdx})`
                          )
                        }
                      >
                        View real photo
                      </button>
                      {heroPromptNote && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{
                            padding: '4px 8px',
                            fontSize: 11,
                            background: showPromptNote ? 'rgba(66, 133, 244, 0.25)' : 'rgba(255, 255, 255, 0.08)',
                            border: '1px solid rgba(255, 255, 255, 0.2)',
                            color: showPromptNote ? '#93c5fd' : '#e2e8f0',
                            borderRadius: 'var(--radius-sm)'
                          }}
                          onClick={() => setShowPromptNote((prev) => !prev)}
                          title="Ver u ocultar el prompt exacto enviado a Vertex AI Imagen 3"
                        >
                          {showPromptNote ? '✕ Ocultar prompt' : '👁️ Ver prompt'}
                        </button>
                      )}
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
                  </div>
                  {showPromptNote && heroPromptNote && (
                    <div
                      style={{
                        fontSize: 10,
                        color: '#e2e8f0',
                        background: 'rgba(15, 23, 42, 0.92)',
                        border: '1px solid rgba(66, 133, 244, 0.35)',
                        padding: '8px 10px',
                        borderRadius: 'var(--radius-sm)',
                        lineHeight: 1.45,
                        wordBreak: 'break-word',
                        marginTop: 2
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4, color: 'var(--color-accent)', fontWeight: 600, fontSize: 9, letterSpacing: '0.05em' }}>
                        <span>VERTEX AI IMAGEN 3 PROMPT PAYLOAD</span>
                        <button
                          type="button"
                          onClick={() => setShowPromptNote(false)}
                          style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 0 }}
                          title="Cerrar prompt"
                        >
                          ✕
                        </button>
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono, monospace)' }}>
                        {heroPromptNote}
                      </span>
                    </div>
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
                gridTemplateColumns:
                  viewportMode === 'mobile'
                    ? 'repeat(2, minmax(0, 1fr))'
                    : 'repeat(auto-fill, minmax(150px, 1fr))',
                gap: 12,
                padding: 16
              }}
            >
              {related.map((p) => (
                <div key={p.sku} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div
                    style={{
                      position: 'relative',
                      aspectRatio: '4 / 3',
                      borderRadius: 'var(--radius-sm)',
                      background: 'linear-gradient(160deg, var(--color-neutral-800), var(--color-neutral-900))',
                      overflow: 'hidden',
                      display: 'flex',
                      alignItems: 'flex-end',
                      padding: 8,
                      fontSize: 10,
                      color: 'var(--color-neutral-300)'
                    }}
                  >
                    <img
                      src={`/api/assets/hero/${e.g.id}?sku_id=${encodeURIComponent(p.sku)}&style_theme=${encodeURIComponent(p.theme)}`}
                      alt={p.name}
                      loading="lazy"
                      title="Click to inspect full real photo & zoom"
                      onClick={() =>
                        openPhotoLightbox(
                          `/api/assets/hero/${e.g.id}?sku_id=${encodeURIComponent(p.sku)}&style_theme=${encodeURIComponent(p.theme)}`,
                          `${p.name} (${p.sku}) · ${p.theme.replace(/_/g, ' ')}`
                        )
                      }
                      style={{
                        position: 'absolute',
                        inset: 0,
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        opacity: 1,
                        filter: 'none',
                        mixBlendMode: 'normal',
                        cursor: 'zoom-in'
                      }}
                    />
                    <span
                      style={{
                        position: 'relative',
                        zIndex: 1,
                        background: 'color-mix(in srgb, var(--color-bg) 78%, transparent)',
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)'
                      }}
                    >
                      {p.sku}
                    </span>
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

            {/* Authentic Storefront Luxury Brand Footer */}
            <footer
              style={{
                padding: '24px 20px 32px',
                borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                background: '#090d16',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                fontSize: 11,
                color: '#64748b',
                textAlign: 'center',
                userSelect: 'none'
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  gap: 12,
                  flexWrap: 'wrap',
                  color: '#94a3b8',
                  fontWeight: 500
                }}
              >
                <span>AtelierNova Maison</span>
                <span>·</span>
                <span>London · Milan · Paris · Zurich</span>
                <span>·</span>
                <span>White-Glove Delivery</span>
                <span>·</span>
                <span>30-Day Atelier Trial</span>
              </div>
              <p style={{ margin: 0, fontSize: 10, color: '#475569' }}>
                Curated architectural design tailored for European living spaces. All rights reserved © 2026 AtelierNova.
              </p>
            </footer>
          </div>

          {/* Smartphone Home Indicator for Mobile Simulation */}
          {viewportMode === 'mobile' && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 16px 8px',
                background: '#0f172a',
                borderTop: '1px solid rgba(255,255,255,0.06)',
                flexShrink: 0
              }}
            >
              <button
                type="button"
                onClick={() => setPreviewHeightMode((m) => (m === 'device' ? 'full' : 'device'))}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: 10,
                  color: '#64748b',
                  cursor: 'pointer'
                }}
                title={previewHeightMode === 'device' ? 'Expandir tienda a toda la altura' : 'Volver a marco móvil'}
              >
                {previewHeightMode === 'device' ? '⤢ Expandir' : '📱 Marco móvil'}
              </button>
              <div
                style={{
                  width: 120,
                  height: 4,
                  background: '#475569',
                  borderRadius: 2
                }}
              />
              <span style={{ fontSize: 10, color: '#475569' }}>iOS 18</span>
            </div>
          )}
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
                  setCustomHeroSrc(null);
                  setHeroImgFailed(false);
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
                <strong style={{ fontWeight: 600, color: 'var(--color-warning-text)' }}>
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

        {/* Full-Resolution Real Photo Lightbox & Pinch-to-Zoom Inspector */}
        {lightboxOpen && (
          <div
            data-testid="real-photo-lightbox"
            role="dialog"
            aria-modal="true"
            aria-label="Full resolution real photo inspector"
            onClick={(ev) => {
              ev.stopPropagation();
              setLightboxOpen(false);
            }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 120,
              background: 'rgba(10, 14, 23, 0.92)',
              backdropFilter: 'blur(10px)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              padding: '16px 20px',
              color: '#f8fafd',
              userSelect: 'none'
            }}
          >
            {/* Top Controls Bar */}
            <div
              onClick={(ev) => ev.stopPropagation()}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 12,
                padding: '10px 16px',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(30, 41, 59, 0.88)',
                border: '1px solid rgba(148, 163, 184, 0.25)'
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span className="mono" style={{ fontSize: 10, color: '#93c5fd', textTransform: 'uppercase' }}>
                  Real Unfiltered Asset · Pinch or Scroll to Zoom (100% – 400%)
                </span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{lightboxCaption}</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  data-testid="lightbox-zoom-out"
                  aria-label="Zoom out"
                  className="btn btn-secondary"
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  disabled={zoomLevel <= 1}
                  onClick={() => updateZoom(zoomLevel - 0.5)}
                >
                  −
                </button>
                <span
                  data-testid="lightbox-zoom-level"
                  className="mono tabular-nums"
                  style={{ fontSize: 12, minWidth: 48, textAlign: 'center', color: '#f8fafd' }}
                >
                  {Math.round(zoomLevel * 100)}%
                </span>
                <button
                  type="button"
                  data-testid="lightbox-zoom-in"
                  aria-label="Zoom in"
                  className="btn btn-secondary"
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  disabled={zoomLevel >= 4}
                  onClick={() => updateZoom(zoomLevel + 0.5)}
                >
                  +
                </button>
                <button
                  type="button"
                  data-testid="lightbox-zoom-reset"
                  className="btn btn-ghost"
                  style={{ padding: '4px 10px', fontSize: 11, color: '#f8fafd' }}
                  onClick={() => {
                    setZoomLevel(1);
                    setPanOffset({ x: 0, y: 0 });
                  }}
                >
                  Reset 100%
                </button>
                <a
                  href={lightboxSrc}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="lightbox-open-original"
                  className="btn btn-ghost"
                  style={{ padding: '4px 10px', fontSize: 11, color: '#93c5fd', textDecoration: 'none' }}
                >
                  Open original ↗
                </a>
                <button
                  type="button"
                  data-testid="lightbox-close"
                  className="btn btn-primary"
                  style={{ padding: '4px 12px', fontSize: 11 }}
                  onClick={() => setLightboxOpen(false)}
                >
                  Close photo
                </button>
              </div>
            </div>

            {/* Interactive Pinch-to-Zoom & Pan Stage */}
            <div
              data-testid="lightbox-stage"
              onClick={(ev) => ev.stopPropagation()}
              onDoubleClick={() => {
                if (zoomLevel > 1) {
                  setZoomLevel(1);
                  setPanOffset({ x: 0, y: 0 });
                } else {
                  setZoomLevel(2.5);
                }
              }}
              onWheel={(ev) => {
                ev.preventDefault();
                const delta = ev.deltaY < 0 ? 0.25 : -0.25;
                updateZoom(zoomLevel + delta);
              }}
              onTouchStart={(ev) => {
                if (ev.touches.length === 2) {
                  const dx = ev.touches[0].clientX - ev.touches[1].clientX;
                  const dy = ev.touches[0].clientY - ev.touches[1].clientY;
                  pinchStartDistRef.current = Math.hypot(dx, dy);
                  pinchStartZoomRef.current = zoomLevel;
                } else if (ev.touches.length === 1 && zoomLevel > 1) {
                  dragStartRef.current = {
                    x: ev.touches[0].clientX,
                    y: ev.touches[0].clientY,
                    origX: panOffset.x,
                    origY: panOffset.y
                  };
                }
              }}
              onTouchMove={(ev) => {
                if (ev.touches.length === 2 && pinchStartDistRef.current) {
                  const dx = ev.touches[0].clientX - ev.touches[1].clientX;
                  const dy = ev.touches[0].clientY - ev.touches[1].clientY;
                  const dist = Math.hypot(dx, dy);
                  const scaleRatio = dist / Math.max(1, pinchStartDistRef.current);
                  updateZoom(pinchStartZoomRef.current * scaleRatio);
                } else if (ev.touches.length === 1 && dragStartRef.current && zoomLevel > 1) {
                  setPanOffset({
                    x: dragStartRef.current.origX + (ev.touches[0].clientX - dragStartRef.current.x),
                    y: dragStartRef.current.origY + (ev.touches[0].clientY - dragStartRef.current.y)
                  });
                }
              }}
              onTouchEnd={() => {
                pinchStartDistRef.current = null;
                dragStartRef.current = null;
              }}
              onMouseDown={(ev) => {
                if (zoomLevel > 1) {
                  dragStartRef.current = {
                    x: ev.clientX,
                    y: ev.clientY,
                    origX: panOffset.x,
                    origY: panOffset.y
                  };
                }
              }}
              onMouseMove={(ev) => {
                if (dragStartRef.current && zoomLevel > 1) {
                  setPanOffset({
                    x: dragStartRef.current.origX + (ev.clientX - dragStartRef.current.x),
                    y: dragStartRef.current.origY + (ev.clientY - dragStartRef.current.y)
                  });
                }
              }}
              onMouseUp={() => {
                dragStartRef.current = null;
              }}
              onMouseLeave={() => {
                dragStartRef.current = null;
              }}
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                touchAction: 'none',
                cursor: zoomLevel > 1 ? 'grab' : 'zoom-in',
                margin: '12px 0'
              }}
            >
              <img
                src={lightboxSrc}
                alt={lightboxCaption}
                data-testid="real-photo-lightbox-img"
                draggable={false}
                style={{
                  maxWidth: '92vw',
                  maxHeight: '76vh',
                  objectFit: 'contain',
                  opacity: 1,
                  filter: 'none',
                  mixBlendMode: 'normal',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: '0 24px 64px rgba(0, 0, 0, 0.65)',
                  transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
                  transformOrigin: 'center center',
                  transition: pinchStartDistRef.current || dragStartRef.current ? 'none' : 'transform 140ms ease-out'
                }}
              />
            </div>

            {/* Bottom Help Bar */}
            <div
              onClick={(ev) => ev.stopPropagation()}
              style={{
                textAlign: 'center',
                fontSize: 11,
                color: '#cbd5e1'
              }}
            >
              Double-click image to toggle 250% zoom · Pinch with 2 fingers or scroll wheel to zoom · Drag to pan · Press Esc to close
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

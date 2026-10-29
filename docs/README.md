# 📚 Documentación y Cuaderno de Bitácora — Mesa T02 (`t02_dynamic_storefronts`)

Bienvenido al directorio de documentación técnica, metodología de trabajo y **Cuaderno de Bitácora** de la **Mesa T02 (Visual Content Creator & Dynamic Storefronts — AtelierNova Home & Lifestyle)** en el **AI Innovators Expedition Hackathon (Google London, 29–30 Octubre 2026)**.

---

## 🧭 Índice de Documentos

| Documento | Propósito | Fase / Alcance |
| :--- | :--- | :--- |
| **[`BITACORA_T02.md`](./BITACORA_T02.md)** | **Cuaderno de Bitácora Maestro y Guía de Trabajo del Challenge**: Cómo indica el reto que debemos trabajar (Must-Haves, Agentic SDLC, `git worktree`, TDD, PRs) y registro cronológico detallado de **todas las fases desarrolladas (Fases 0 a 4)** con arquitectura, decisiones, pruebas y trazabilidad. | **Todas las Fases (0–4)** |
| **[`PHASE1_SPEC.md`](./PHASE1_SPEC.md)** | **Especificación Técnica — Fase 0 y Fase 1 (1A + 1B)**: Los 5 Must-Haves, Pipeline CI/CD dividido (GitHub Actions + Cloud Build), Prácticas Agentic SDLC y Guardrails de Seguridad/Margen contra *Discount Injection* (`SKU-0017` y `SKU-0085`). | **Fase 0, Fase 1A y Fase 1B** (`Issues #1, #2, #3` · `PR #8, #10`) |
| **[`PHASE2_SPEC.md`](./PHASE2_SPEC.md)** | **Especificación Técnica — Fase 2 (2A + 2B)**: Analítica avanzada en BigQuery con `INNER JOIN` de 3 tablas (`recommend_storefront_optimization`), generación multimodal de imágenes hero (`generate_hero_lifestyle_image` con `gemini-3.1-flash-image`) y preview UI interactiva (`render_storefront_preview`). | **Fase 2A y Fase 2B** (`Issues #4, #5` · `PR #7`) |
| **[`PHASE3_SPEC.md`](./PHASE3_SPEC.md)** | **Especificación Técnica — Fase 3**: Protocolo Tribe A2A Handshake (`sync_campaign_with_t01`) con la Mesa Hermana **Table 1 (`t01_campaign_orchestrator`)** y plantilla HTML5/CSS editable (`seed_packs/t02_dynamic_storefronts/ui/`). | **Fase 3** (`Issue #6` · `PR #9`) |
| **[`PITCH_T02.md`](./PITCH_T02.md)** | **Storyboard del Pitch (2 Slides) y Runbook de Demo en Vivo (3:00 min / 5:00 Hard Stop)**: Guion minuto a minuto para los jueces, comandos para levantar la UI y prompts exactos de demostración. | **Fase 4 (Pitch & Demo)** (`Issue #6` · `PR #9`) |
| **[`STARTER.md`](./STARTER.md)** | Referencia técnica oficial del Starter Kit (arquitectura ADK, contrato de plugins de Seed Packs, despliegue en Vertex AI Agent Runtime y recetas de Bonus). | Referencia Base Hackathon |
| **[`PREWORK.md`](./PREWORK.md)** | Lista de verificación previa al evento (configuración de Antigravity 2.0, `gcloud`, `uv`, Python 3.12 y resumen de las 10 mesas). | Pre-Work |

---

## 🛠️ Cómo Revisar este Worktree Rápidamente

Este trabajo se ha documentado siguiendo el **Pilar 3 de Agentic SDLC** en un worktree aislado (`../wt-docs-logbook`, rama `docs/challenge-workflow-and-logbook`) para no interferir con otros agentes o ramas activas:

```bash
# 1. Ver todos los worktrees activos del equipo
git worktree list

# 2. Entrar al worktree de documentación y bitácora
cd ../wt-docs-logbook

# 3. Ejecutar la suite de tests offline y validar los casos golden
make test
make eval-validate PACK=t02
```

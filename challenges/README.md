# Challenge Card — Table 2 (`T02-dynamic_storefronts`)

> **Note:** This repository is scoped to **Table 2 — Visual Content Creator & Dynamic Storefronts** (`SEED_PACK=t02`, directory `seed_packs/t02_dynamic_storefronts`) within the **Creative AI & AdTech** Tribe, paired with Sister **Table 1** (`seed_packs/t01_campaign_orchestrator`) for the **Tribe A2A Bonus**.
>
> *All companies, personas, datasets, and mock APIs described in this Challenge Card are 100% synthetic and fictional.*

---

## Active Challenge & Tribe Overview

| Table | Challenge Card | Tribe | Collaborative Challenge Title | Sister Table (Tribe A2A) | Seed Pack Directory | Security & Guardrails Test Vector (Optional +1 Bonus) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **T02** | [`T02-dynamic_storefronts.md`](./T02-dynamic_storefronts.md) | Creative AI & AdTech | **Visual Content Creator & Dynamic Storefronts** | **T01** (`t01_campaign_orchestrator`) | [`seed_packs/t02_dynamic_storefronts`](../seed_packs/t02_dynamic_storefronts/) | Untrusted Catalog Metadata Discount Injection (`discount_pct=95` override on `SKU-0017`) |
| **T01** *(Sister Table — A2A)* | [`seed_packs/t01_campaign_orchestrator/CHALLENGE_CARD.md`](../seed_packs/t01_campaign_orchestrator/CHALLENGE_CARD.md) | Creative AI & AdTech | **Autonomous Creative Campaign Orchestrator** | **T02** (`t02_dynamic_storefronts`) | [`seed_packs/t01_campaign_orchestrator`](../seed_packs/t01_campaign_orchestrator/) | Poisoned Event Brief / Ad Copy Injection (`target_cpm_bid_eur <= 25.00` cap) |

---

## How to Run Table 2 (`t02_dynamic_storefronts`)

```bash
# 1. Configure .env (defaults to SEED_PACK=t02)
cp .env.example .env
# Edit .env: set GOOGLE_CLOUD_PROJECT=<your-project-id> and SEED_PACK=t02

# 2. Load Table 2's synthetic CSVs into BigQuery (seed_t02) in your project
make seed PACK=t02

# 3. Run offline tests + evaluation schema + pack validator
make verify PACK=t02

# 4. Launch the ADK Web UI locally or run live golden evaluations
make dev
make eval PACK=t02
```

For the complete engineering logbook and phase specifications of our Table 2 implementation, see [`docs/README.md`](../docs/README.md) and [`docs/BITACORA_T02.md`](../docs/BITACORA_T02.md).

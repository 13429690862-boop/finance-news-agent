# Phase 7: Dual-track demand classification

Phase 7 adds a deterministic classification layer that lets the system capture short-term, manually serviceable demand without weakening the existing long-term product opportunity filter.

## Track A: Quick Service Leads

Quick service leads are individual or small-business requests that can plausibly be handled manually or through a lightweight service. Examples include:

- help buying from 1688, Taobao, or Alibaba;
- sourcing-agent or supplier-contact help;
- supplier verification, factory audits, QC inspections, or pre-shipment checks;
- freight forwarding, DDP shipping, or customs documentation guidance;
- WeChat Pay or Alipay integration guidance;
- Chinese localization, China customer-support setup, fapiao/invoice workflow, address validation, or other legitimate China-facing workflow setup.

A quick service lead requires source-primary title/content evidence for all three of these categories:

1. a requester/customer/actor signal such as “I need,” “looking for,” “can someone help,” “we need,” or “our company needs”;
2. a China-related workflow such as 1688/Taobao buying, supplier verification, freight forwarding, WeChat Pay/Alipay, localization, fapiao, Shenzhen/Yiwu/manufacturer workflows;
3. a concrete deliverable/action such as set up, integrate, verify, source, inspect, ship, translate/localize, contact supplier, purchase/order, or handle documentation.

Quick service leads do **not** require repeated-market evidence, multiple sources, a product opportunity score, or final product-opportunity filter approval. They are emitted before the strict Track-B final filter would discard personal requests.

## Track B: Product Opportunities

Product opportunities remain scalable, repeated-demand opportunities suitable for a productized service, SaaS, agency offer, marketplace, automation, data product, or long-term business. The existing deterministic final opportunity filter remains authoritative. AI enrichment can assist only within configured stages and cannot bypass deterministic rejection. Quick service lead detection does not contaminate product opportunity scoring.

## Requester attribution

Requester attribution is intentionally conservative:

- HN Algolia: uses public `author` and derives `https://news.ycombinator.com/user?id=<author>` when an author is present.
- StackExchange: uses public `owner.display_name`, `owner.link`, and `owner.user_id` when returned by the API.
- GDELT/news: requester is normally `unknown`/supporting evidence, not the journalist, company, or person mentioned in the story.
- Fallback: requester is `unknown`.

The system does not infer real identities from usernames. `contact_allowed=false` by default; source reply/profile review is a manual operator action, not an automated workflow. Emails and phone numbers that appear in public source text are redacted in excerpts and should be treated as sensitive.

## Compliance risk levels

- `low`: ordinary legitimate service request with no sensitive indicators.
- `medium`: sensitive trade/customs/regulatory context that needs manual review.
- `high`: ambiguous payment/account setup or similarly sensitive workflow; suggested next step is compliance review and legitimate guidance only.
- `blocked`: disallowed workflow.

Blocked categories include identity or KYC evasion, fake account creation, buying/selling WeChat or Alipay accounts, payment fraud, credential sharing, sanctions/export-control evasion, illegal or regulated goods, impersonation, scraping private data, and spam/SEO outreach. The system must not support bypassing platform rules, fraud, evasion, or abuse.

## Daily report usage

Use **Quick Service Leads** for manual review of possible short-term service revenue. Confirm legitimacy, scope, and compliance before any human follow-up. Do not auto-contact. Do not scrape private data. Do not infer identity.

Use **Product Opportunities** for long-term validation. These remain stricter and should be validated with repeated source-primary evidence before product or go-to-market investment.

The JSON summary exposes separate `quick_service_leads` and `product_opportunities` arrays plus summaries for quick leads, product opportunities, requester attribution, and compliance. Backward-compatible `opportunities`, `total_opportunities`, `priority_counts`, `final_filter_summary`, `timing_diagnostics`, and `ai_triage_summary` remain present.

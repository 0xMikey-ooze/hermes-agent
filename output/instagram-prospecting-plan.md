# Lead-Gen Plan: Find businesses missing a website/phone, pitch via Instagram

**Status:** Research / plan only (no code yet)
**Chosen approach:** Google Places discovery + Instagram enrichment
**Target home in repo:** `skills/lead-gen/instagram-prospecting/` (new skill on top of existing Hermes tools)

---

## 1. The core insight

The original idea — "crawl Instagram to find businesses with no website/phone" — has the data backwards. Instagram is bad at *discovery* and bad at the *negative signal* you care about:

- IG has no "list all businesses in city X / category Y" endpoint.
- IG's official API (`business_discovery`) returns a profile's bio `website` but **never exposes phone numbers**.
- Direct scraping of instagram.com breaks Meta ToS and gets accounts/IPs banned.

**Google Places is the opposite:** it discovers businesses in bulk by area + category and returns `website` and `internationalPhoneNumber` as explicit, structured fields. So:

> **Discover + filter on Google Places. Use Instagram as the *enrichment + pitch hook*, not the source.**

The pitch writes itself: "You post on Instagram every week but have no website — your customers can't find you on Google. I can fix that in a week."

---

## 2. Pipeline architecture

```
[1] DISCOVER          Google Places Text Search / Nearby Search
     (area+category)   → list of place_ids
        |
[2] DETAIL            Google Places Place Details
     (per place)       → name, website, phone, rating, address, maps URL
        |
[3] FILTER            keep rows where website == null  OR  phone == null
        |
[4] ENRICH (IG)       Firecrawl search "<name> <city> instagram"
     (per lead)        → IG handle, follower count, bio link, post recency
        |
[5] SCORE             rank by: active-on-IG + missing-website + good-rating
        |
[6] PITCH             LLM-drafted, per-lead message (DM / email / call script)
        |
[7] OUTPUT/DELIVER    CSV/JSON + optional draft into Gmail / CRM
```

### Maps onto existing Hermes capabilities
| Step | Existing piece | New code needed |
|------|----------------|-----------------|
| 1–3 Places | none | thin Places API client (~150 LOC) |
| 4 IG enrich | `tools/web_tools.py` (Firecrawl search/extract) | reuse |
| 5 Score | LLM via `agent/auxiliary_client.py` | scoring fn |
| 6 Pitch | LLM | prompt template |
| 7 Deliver | Gmail MCP (`create_draft`), CRM MCP (Intercom-style), messaging gateways | glue |

---

## 3. Why Instagram alone fails (reference)

| Need | Instagram | Google Places |
|------|-----------|---------------|
| Bulk discovery by area/category | ❌ none | ✅ Text/Nearby Search |
| Has a website? | ⚠️ bio link only, via API by-username | ✅ `websiteUri` field |
| Has a phone? | ❌ not in API | ✅ `internationalPhoneNumber` |
| ToS / ban risk | 🔴 high (scraping) | 🟢 official paid API |
| Cost | scraper actors ~$1–3/1k | see §5 |

Instagram's `business_discovery` also requires *your own* FB Page + IG Business account and only works one username at a time — useless for finding leads you don't already know.

---

## 4. Data model (lead record)

```json
{
  "place_id": "ChIJ...",
  "name": "Cafe Example",
  "category": "coffee_shop",
  "address": "123 Main St, Austin, TX",
  "maps_url": "https://maps.google.com/?cid=...",
  "website": null,
  "phone": "+1 512 555 0100",
  "rating": 4.6,
  "review_count": 212,
  "missing": ["website"],
  "instagram": {
    "handle": "@cafeexample",
    "url": "https://instagram.com/cafeexample",
    "followers": 3400,
    "bio_link": null,
    "last_post_days_ago": 2
  },
  "score": 87,
  "pitch": { "channel": "instagram_dm", "draft": "Hey ..." },
  "status": "new"
}
```

Persist as JSONL in `output/leads/` (matches Hermes' file-based, no-DB convention) or push to the connected CRM.

---

## 5. Cost & quota reality (Google Places, 2026)

- **Text Search / Nearby Search** and **Place Details** are billed per request; cost depends on which field tiers (`Basic` / `Contact` / `Atmosphere`) you request. `website` + `phone` fall in the **Contact** tier, which is priced higher than Basic — request *only* the fields you need via a field mask to control spend.
- Google provides a recurring monthly free credit; a single-city prospecting run of a few hundred businesses typically lands within or near it.
- **Action item before building:** confirm current per-1k pricing and the free-tier credit in the Google Cloud console, since Google reshuffled Places (New) pricing tiers. Budget guard: cap requests per run and reuse `agent/metrics.py` cost-tracking patterns.
- Firecrawl enrichment cost is per search/extract — already a Hermes dependency, so it rides existing budget controls.

---

## 6. Compliance / risk notes

- **Google Places**: official API, ToS-clean. Watch the caching restriction — Places content (esp. `place_id` aside) has limited allowed caching durations; don't build a permanent shadow database of Google content.
- **Instagram enrichment via Firecrawl**: reading public profile data is lower-risk than authenticated scraping, but still don't automate logged-in actions or mass-DM through unofficial endpoints — that's what gets accounts banned.
- **Outreach/anti-spam**: cold outreach is regulated (CAN-SPAM for email, platform DM limits, and in some regions GDPR/CASL). Keep volume human-paced, include opt-out on email, and don't auto-blast. Pitch *drafts* for human review beat full auto-send.
- **Honest pitch**: the "missing website" claim must be true at send time — re-verify before sending, businesses add sites.

---

## 7. Suggested build phases (when you greenlight code)

1. **Phase 1 — Discovery core**: Places client (search + details + field mask), filter for missing website/phone, output JSONL + CSV. *Deliverable: a list of qualified leads from one city/category.*
2. **Phase 2 — IG enrichment**: Firecrawl lookup of handle + follower + post recency; scoring. *Deliverable: ranked leads with the pitch hook.*
3. **Phase 3 — Pitch generation**: per-lead LLM drafts (DM / email / call script) in the Hermes/SOUL voice.
4. **Phase 4 — Delivery + tracking**: draft into Gmail/CRM (MCP tools are available in this env), status tracking, dedupe across runs, budget caps.

Package the whole thing as a Hermes skill so the agent can run it on a schedule (cron) and report leads to a messaging channel.

---

## 8. Open questions to resolve before coding

1. Target geography + business categories for the first run?
2. Filter logic: leads missing website **OR** phone, or strictly **no website**?
3. Outreach channel priority: IG DM, email, or phone-call scripts?
4. Auto-draft only (human sends) vs. attempt automated send? (Strongly recommend draft-only to start.)
5. Do you already have a Google Cloud project / Places API key, or does provisioning that need to be in scope?

# Discord Growth & Subscription Conversion Plan

> **Goal:** Get more people to discover and join Discord, while raising BigTreeSignal subscription rate.  
> **Principle:** Acquire outside + convert inside. Discord is where you retain and close — not where strangers discover you.  
> **Constraints:** Follow Discord ToS and financial-content compliance; no cold mass DMs to strangers, no server spam, no buying members.

Related docs: [`PROMOTION_DESIGN.md`](../archive/PROMOTION_DESIGN.md) (in-server promos), [`FEATURE_LIST.md`](../features/FEATURE_LIST.md) (features 57–62 acquisition & conversion).

---

## 1. Bottom Line First

The existing bot **already can push “people who joined” toward subscribe** (welcome drip, purchase intent, YouTube summary CTA, `/invite`, funnel). Growth is stuck because **not enough people join**, not because in-server promos are under-sent.

So this plan has two halves that must run together:

| Half | Problem to solve | Current state |
|------|------------------|---------------|
| **Acquisition (off-server)** | How strangers hear about you the first time | Almost blank — needs new features |
| **Conversion (in-server)** | How joiners trial / pay | Features exist — turn them on and add tracking |

Success formula:

```
Public content (searchable)
    → Landing page / invite link with channel codes (trackable)
    → Discord join
    → First 10 minutes experience + 24–72h drip
    → Trial
    → Subscribe
```

Only acquire, never convert → subscription rate falls. Only convert, never acquire → subscriber count caps out. Watch both sides.

---

## 2. You vs AI vs New Features (Master Table)

| Layer | You (channel owner) do | AI / automation does | New features needed |
|-------|------------------------|----------------------|---------------------|
| **Positioning & compliance** | Set public slogan, disclaimers, what can go public | Append disclaimer templates to every public draft | Public content sanitizer |
| **Tracking** | Create one invite code each for YouTube / X / Xiaohongshu / partners | Record join source, write funnel | Channel invite codes + source funnel |
| **Content** | Review 5–10 min/day; personally post on 1–2 main platforms | Generate 4 off-server drafts from daily highlights | Content factory + Owner review queue |
| **Distribution** | Partnerships, short videos, reply to comments | Export copy after approval; later optional platform APIs | Distribution export / optional auto-post |
| **Virality** | Reward roles; pin “share for rewards” | `/invite` attribution, monthly board, one-click public pack | Invite monthly board + `/share` |
| **Conversion** | Real trial URL, VIP role, welcome copy | Welcome drip, intent detection, CTA buttons | Track “spoke within 7 days of join” |
| **Decisions** | Weekly funnel review; double down on winners, kill losers | `/funnel` broken down by source | Growth dashboard |

---

## 3. Current State: Capabilities vs Gaps

### Already built (in-server conversion — turn on first)

| Capability | Module | Role |
|------------|--------|------|
| Purchase intent → product CTA + notify you | `bot/acquisition.py` | Close when someone asks price/trial |
| New member 24–72h drip | `bot/welcome_flow.py` | Welcome → proof → CTA → reminder |
| YouTube new video → summary + CTA | `bot/youtube_monitor.py` | Education that also acquires |
| `/invite` personal invite + reward role | `bot/acquisition_cog.py` | Member referrals |
| `/funnel` funnel | `bot/acquisition.py` | Joins / welcome / intent / CTA |
| Daily/weekly summaries | `bot/daily_summary.py`, `bot/weekly_summary.py` | **Best raw material for public content** |
| Testimonial review | `bot/testimonials.py` | Social proof |
| Opt-in notify DMs | `bot/role_dm.py` | Only message people who clicked “Claim notify” |

Note: `WELCOME_FLOW_ENABLED` defaults to `false`. If the conversion funnel is off, more joins still churn.

### Gaps (off-server acquisition — this plan builds)

1. No “public publish pack”: daily summaries stay locked in Discord; Google / Xiaohongshu cannot find them.
2. Invite links lack a **channel dimension** (member personal codes only — no `youtube` / `xhs`).
3. No landing page: strangers clicking `discord.gg` do not know what is inside.
4. No public review queue: financial content cannot auto-post to the open web.
5. Funnel lacks full “source → join → speak → trial → paid” chain.
6. 5000 members are not a stable distribution network (`/invite` exists; missing monthly board and one-click share packs).

---

## 4. What to Measure (or you spin wheels)

Track only these 6 numbers weekly with `/funnel` and the growth dashboard:

| Metric | Meaning | Healthy direction |
|--------|---------|-------------------|
| **Joins by channel** | New members per invite code per week | Find 1–2 channels worth doubling |
| **7-day activation rate** | Spoke or used `/ask` within 7 days of join | Target ≥ 20%; low = welcome-flow problem |
| **Intent count** | People who asked price/trial | Whether content attracts “signal buyers” |
| **Trial clicks** | CTA / trial buttons | Whether product/trial URLs work |
| **Paid count** | Actual subscriptions (you or payment webhook) | North star |
| **Referral share** | `invite_joins` / `joins` | Healthy communities rise slowly |

Joins without a source are always logged as `unknown` — force yourself to split links.

---

## 5. Phased Plan

### Phase 0 — Turn On Existing Conversion (~1 week, almost no code)

**Purpose:** New joiners should not be wasted. Raise subscription rate via conversion first, then traffic.

**You do:**

1. In `.env`, enable and fill real URLs (no placeholder domains):
   - `WELCOME_FLOW_ENABLED=true`
   - `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_URL`, `FREE_TRIAL_ENABLED=true`
   - `INTENT_CONVERT_ENABLED=true`, `INTENT_LEAD_ROLE_ID` (consulting role)
   - `INVITE_TRACKING_ENABLED=true`, `INVITE_REWARD_ROLE_ID`, thresholds
   - `YOUTUBE_MONITOR_ENABLED=true` and channel IDs
   - `DAILY_SUMMARY_ENABLED=true`
   - `PROMO_NOTIFY_ROLE_IDS` + `/promo_notify_panel` in an announcement channel
2. In Discord, create a **permanent invite** per channel (or wait for Phase 1 channel codes): YouTube, X, Xiaohongshu, partners, word-of-mouth.
3. Server description, tags, Vanity URL: include “US stocks / equity analysis”.
4. Public welcome channel: rules in 30 seconds, today’s highlights, how to `/ask`, how to `/signal`.
5. Confirm bot can: create/view invites, Server Members Intent, manage target roles.

**AI / automation does:** Existing modules run welcome drip, intent CTA, YouTube summary buttons, invite attribution.

**New features:** None. First prove funnel numbers move.

**Done when:** `/funnel` shows joins, welcome_dm_ok, intent_hits; trial links open.

---

### Phase 1 — Content Factory (~2–3 weeks, core new features)

**Purpose:** Turn analysis already produced in-channel into searchable, shareable public content. This is the main acquisition engine.

#### You do

- Set 3 public red lines: no others’ positions/P&L, no unreviewed entries/exits, every piece carries a disclaimer.
- Fixed 5–10 minutes/day: Approve / Edit / Discard in the review queue.
- Personally run **1 main platform** (suggest YouTube Shorts or X); reply in comments and place invite links.
- Do not chase daily posts on 6 platforms; one platform done well beats six nobody reads.

#### AI / automation does

Each day after daily summary generation (reuse `daily_summary.py` feedstock):

1. Pick 1 high-engagement theme (optionally using day’s message heat).
2. Produce a **public publish pack** (strip member names, private numbers; add disclaimer).
3. Simultaneously output 4 drafts:
   - 60–90s spoken script (short video)
   - X / Twitter thread (8–12 posts)
   - Xiaohongshu image post (title + body + tags)
   - SEO short article title + body (landing / blog)
4. Append that day’s **default channel invite link** at the end of each draft.
5. Drafts enter Owner review queue (reuse `review.py` Approve / Edit / Reject pattern). **Default: never auto-publish publicly.**

#### New features to build

| Feature | Suggested file | Notes |
|---------|----------------|-------|
| **Public content sanitizer** | `bot/growth_sanitize.py` | Strip @mentions, user IDs, private P&L, internal channel names; force disclaimer |
| **Content factory** | `bot/growth_factory.py` | Daily summary + RAG style → 4 off-server draft JSON |
| **Growth review queue** | `bot/growth_review.py` | DM you for review; on pass write `data/growth_pack.json` |
| **`/growth_pack`** | `bot/commands.py` | Owner generate today’s pack now, or list pending |
| **Channel invite codes** | Extend `bot/acquisition.py` | Preset `youtube` / `xhs` / `twitter` / `partner` / `organic`; record source on join |
| **Funnel source fields** | `data/funnel.json` | `joins_by_source`; `/funnel` by channel |

**Done when:** 5 consecutive trading days produce a copyable four-pack after your review; at least 1 off-server platform posts daily or weekly.

---

### Phase 2 — Landing Page + Distribution (~2 weeks)

**Purpose:** Strangers understand value before joining Discord; invite links are trackable.

#### You do

- Prepare 3 anonymized highlight screenshots, a “who this is” intro, final disclaimer copy.
- Domain or existing `web-client` subpath, e.g. `/join`.
- Each platform bio/outro only uses **that platform’s link** (landing `?src=youtube` or matching Discord invite).
- Start partnerships: 1 US-stock creator / newsletter per week, with finished samples not verbal pitch.

#### AI / automation does

- Landing “this week’s highlights” pulls latest approved growth pack.
- Approved drafts one-click export: `.txt` / `.md` / subtitle SRT for pasting to platforms.
- YouTube description template: auto draft timestamps + invite CTA (you paste on upload).

#### New features to build

| Feature | Suggested place | Notes |
|---------|-----------------|-------|
| **Public join page** | New `web-client` route or static page | Positioning, 3 highlights, testimonials, big “Join Discord”, source params |
| **Public API: weekly highlights** | `bot/api/routes_public.py` | Return only approved, sanitized content |
| **`/share`** | `bot/commands.py` | From a message or today’s summary → public pack + that member’s `/invite` link |
| **Export command** | `/growth_export` | Bundle approved drafts as files to your DM |

**Done when:** YouTube traffic shows `youtube` in the funnel; landing page opens alone without forcing Discord first.

---

### Phase 3 — Turn 5000 Members into a Distribution Net (~2 weeks)

**Purpose:** Acquisition shifts from “you alone post” to “members willing to forward”.

#### You do

- Define rewards: N valid invites (spoke within 7 days of join) → role / trial — not cash.
- Pin how-to: `/invite`, `/share`, what can/cannot be shared.
- Publish monthly invite leaderboard (public channel — honor, not harassment).

#### AI / automation does

- Keep existing invite attribution; auto-grant roles at thresholds (already built).
- Monthly board: sort by valid invites.
- Members use `/share` for de-identified copy + their invite code — lower share friction.

#### New features to build

| Feature | Notes |
|---------|-------|
| **Valid invites** | Only count after 7-day activation (anti-farm) |
| **`/invite_leaderboard`** | Monthly board, valid invites only |
| **Share card** | Optional: render public pack as image (title + quote + QR) for Xiaohongshu |

**Done when:** `invite_joins` share of weekly joins rises; a stable top-10 inviters appears.

---

### Phase 4 — Scale Winning Channels (on demand — do not start early)

Only after Phase 1–3 can answer “which channel brings people who speak and ask price”:

| Action | You do | AI does | New feature |
|--------|--------|---------|-------------|
| Platform API direct post | Authorize X / YouTube | Timed post after approval | `bot/growth_publish.py` (still forbid unreviewed publish) |
| Search / feed ads | Buy landing page, not bare invites | Generate 5 ad copy A/B sets | Landing event callbacks |
| Discord Discovery | Enable + complete server profile | — | None |
| Paid write-back | Payment success page or manual `/mark_paid` | Funnel records `paid` | Subscription event API |

Ads without source data means you cannot see ROI.

---

## 6. New Feature Checklist (implementation order)

Treat as separate follow-on work — do not tangle with core RAG.

### Must have (P0)

1. **Channel invite codes & source attribution** — extend `acquisition.py` / `acquisition_cog.py`
2. **7-day activation tracking** — store `joined_at` on join; `activated_at` on speak or `/ask`
3. **Content factory + sanitizer + review queue** — `growth_factory` / `growth_sanitize` / `growth_review`
4. **`/growth_pack`, `/funnel` with sources** — Owner commands

### Strongly recommended (P1)

5. **Public join page + weekly highlights API**
6. **`/share` + `/growth_export`**
7. **Valid invites + `/invite_leaderboard`**
8. **Funnel `trial_clicks` / `paid`** (button clicks + manual/payment write-back)

### Later (P2)

9. Share-card image generation  
10. Auto-publish to X / YouTube after review  
11. Ad copy generation + landing pixels  

### Explicitly do not

- Mass-add friends / DM strangers  
- Join other servers to drop invites  
- Buy members or fake mutual pulls  
- Auto-post unreviewed trade advice publicly  
- Mass DM non-opt-in roles (existing `role_dm.py` already forbids)

---

## 7. Suggested Module Layout (when building)

```
bot/
  growth_sanitize.py    ← public publish rules
  growth_factory.py     ← 4 draft types (LLM + style profile)
  growth_review.py      ← Owner review, reuse Button pattern
  growth_cog.py         ← daily job + slash commands

data/
  growth_pack.json      ← daily drafts / approved packs
  growth_sources.json   ← channel code definitions
  activations.json      ← joins + 7-day activation
```

Daily trigger: hook after existing `DailySummaryCog` successfully posts — avoid rescanning the channel.

Public drafts must use the style profile (`data/style_profile.txt`) so tone matches the channel, but **facts come from that day’s Owner messages** — the model must not invent prices or P&L.

---

## 8. Weekly Rhythm (after Phase 1 ships)

| When | Automation | You |
|------|------------|-----|
| Trading day after close | Daily summary → growth pack → DM review | Approve / Edit / Discard (5–10 min) |
| Same night or next morning | Export four-pack | Post to main platform; outro/comments get channel link |
| Each Sunday | `/funnel` summary DM | Decide which channel to scale; open 1 partnership |
| Month start | Invite monthly board | Grant reward roles; thank by name |

---

## 9. Risk & Compliance

- **Financial content:** Public drafts share one footer: “For educational discussion only; not investment advice.” Entries, exits, and targets stay out of public packs unless you manually add them back in review.
- **Privacy:** Sanitizer removes member names, accounts, UIDs in screenshots; testimonials on the landing page must already be testimonials-approved.
- **Discord:** Invite tracking needs Members Intent; mass DMs only to opt-in notify roles.
- **Brand:** Prefer not posting over letting the model “predict tomorrow must rise” on the public web. The review queue is a feature, not a blocker.

---

## 10. Relation to Subscription Rate (avoid chasing headcount only)

```
Off-server content quality ↑
  → Joiners look more like “want US stocks / want signals”
  → 7-day activation, intent, trial clicks ↑
  → Subscription rate ↑

Off-server content becomes “please join our server”
  → Joiners are filler
  → Activation ↓, subscription rate feels worse
```

So content-factory topics must be **searchable US-stock questions**, with CTA only at the end. Welcome copy and `/signal` close the sale; public content builds trust.

---

## 11. Suggested Next Steps

1. You finish **Phase 0** first (welcome drip on, real product/trial URLs, invite reward role).  
2. After committing to Phase 1, implement P0 from section 6: channel codes, activation tracking, content factory, review queue.  
3. Pick one main platform (YouTube Shorts or X), then open the landing page.

If coding starts, priority order: **channel invite codes → content factory + review → `/share` → landing page**.

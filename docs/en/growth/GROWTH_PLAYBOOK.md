# BigTree Community Activation & Subscription Conversion Playbook

> Audience: ~5000-member Discord community running 5+ years  
> Product sold: Subscription intro channel (BigTreeSignal)  
> Intro page: [Subscription intro channel](https://discordapp.com/channels/895349295975370802/923313988996051005)  
> Close method: After reading the intro, **DM the channel owner** to subscribe  
> Companion features: see [`FEATURE_LIST.md`](../features/FEATURE_LIST.md) items 57–62; promo commands: [`PROMOTION_GUIDE.md`](../operations/PROMOTION_GUIDE.md)

This is an operations handbook for the channel owner: what you do, what Bot/AI does, which week to run which step, and copy you can paste. Do not mass-DM promo messages to members who did not opt in.

---

## 1. Goals & Conversion Path

**Goals (90 days)**

1. Wake dormant members who still have Discord notifications and occasionally open the server  
2. Get them to open the subscription intro channel first  
3. Have interested people DM you to subscribe, raising subscription rate  

**Only close path (do not change)**

```text
Woken by content/announcement
  → Open subscription intro channel (product page)
  → DM channel owner to subscribe
  → You quote, collect payment, add VIP role
```

- **Intro channel** = product page — explains what they buy  
- **DM you** = checkout — where the sale closes  
- **Bot** = guide: wake people, bring them to the intro page, notify you of price inquiries  

You cannot wake 5000 people with mass DMs. Many disable “Allow direct messages from server members”; delivery is poor and complaints rise. Use **announcement channels** to wake; use **intro page + DM you** to subscribe.

---

## 2. Pre-Flight Checklist (what is missing now)

Cross-check your current `.env` and fill gaps before talking conversion.

| Item | State (when this playbook was written) | What you do |
| --- | --- | --- |
| Subscription intro channel URL | Already in `SIGNAL_PRODUCT_URL` | Keep this link as the “Learn about product” button |
| Opt-in “Event notify” role | `PROMO_NOTIFY_ROLE_IDS` empty | Must create and set ID, or you cannot send event DMs and welcome DMs lack claim buttons |
| “Inquiring” role | `INTENT_LEAD_ROLE_ID=0` | Create and set ID; people who ask price / click subscribe get tagged for follow-up |
| VIP role | Confirm `VIP_ROLE_IDS` | Add after close; welcome drip stops |
| Invite reward role | `INVITE_REWARD_ROLE_ID=0` | Optional; fill if active members should pull others back |
| Daily/weekly summary, YouTube, Jin10, FAQ push | Already on | Keep them running |
| Welcome drip | Already on | Only affects **future new joins** — does not wake 5-year members |

Developer Portal must already have **Server Members Intent** and **Message Content Intent** enabled (already enabled in code).

---

## 3. Must-Do Checklist This Week (Week 0)

All of these are Discord admin steps; you can finish steps 1–8 without changing code.

### 1. Create an announcement channel

1. Server Settings → Enable Community (if not already on)  
2. Create a channel of type “Announcement”, e.g. `#announcements`  
3. `@everyone`: View Channel only — do **not** grant Send Messages  
4. Give yourself and the Bot: Send Messages, Mention Everyone, Manage Messages (for pinning)

### 2. Create three roles

| Suggested role name | Permissions | Write to `.env` |
| --- | --- | --- |
| Event notify | No admin permissions | `PROMO_NOTIFY_ROLE_IDS=` |
| Inquiring | No admin permissions | `INTENT_LEAD_ROLE_ID=` |
| VIP (if you do not have one yet) | Match your existing member permissions | `VIP_ROLE_IDS=` |

Then:

- Drag the **Bot role above these three**  
- Enable **Manage Roles** on the Bot role  
- Fill `.env` and **restart the Bot**

Copy role IDs: Server Settings → Advanced → enable Developer Mode → right-click role → Copy ID.

### 3. Confirm who can view the intro channel

[Subscription intro channel](https://discordapp.com/channels/895349295975370802/923313988996051005) recommendations:

- Everyone **can view** (otherwise the “Learn about product” button opens a channel they cannot access)  
- Regular members **cannot chat there** (only you and the Bot can post) — keep it like a product page  

If only VIP can enter that channel today, guide buttons will fail. At minimum let “Inquiring” and everyone view it read-only; exclusive post-purchase content can live in a separate VIP channel.

### 4. Pin the subscription panel

In the announcement channel, type:

```text
/promo_notify_panel
```

**Pin** the message the Bot posts.

### 5. Post the first re-engagement announcement (copy-paste)

Post the following in the announcement channel. Add `@everyone` when you need to wake the whole server (suggest only 1–2 times per quarter):

```text
@everyone

This community has been running for 5 years — many of you may not have dropped in for a while.

We recently automated daily highlights, video summaries, and a Q&A assistant:
• Want the product intro → open the subscription intro channel
• Want event DMs → tap “Claim notify” on the pinned message in this channel (opt-in; cancel anytime)
• Want to subscribe → read the intro, then DM me

Intro channel: https://discordapp.com/channels/895349295975370802/923313988996051005
```

You can also replace “subscription intro channel” with a Discord `#channel-name` mention.

### 6. Prepare your three close scripts (copy-paste in DMs)

**When someone asks about price:**

```text
Hi — the intro is in this channel:
https://discordapp.com/channels/895349295975370802/923313988996051005

After you read it, ask me anything. I’ll handle the subscribe setup for you.
```

**When they say they want to buy:** (replace with your real price and payment method)

```text
Sure. Price is ____, payment via ____.
Send me a payment screenshot when you’re done and I’ll add your VIP.
```

**When they are just browsing again:**

```text
Start with the intro channel. To get event alerts, go to announcements and tap “Claim notify”.
Ready to subscribe? DM me.
```

Without these three lines, you will drop the ball after the Bot routes people into your DMs.

---

## 4. What You Do Daily / Weekly

**Daily (10–20 minutes)**

1. Check the “Inquiring” role in Discord: DM new people within 24 hours (you can start with the first script above)  
2. Check `/funnel days:7`: joins, welcome DM success/reject, `/signal`, purchase intent  
3. Watch the intro and announcement channels for “how do I buy?” — the Bot should already auto-reply; you only need to follow up in DMs  

**Weekly (once)**

1. Confirm daily summary, YouTube digest, and FAQ go out on schedule  
2. For existing ops role groups: in the matching channel, `@that-role` with one worth-reading item this week + intro channel link (not a DM)  
3. If people have claimed “Event notify”: you may `/dm_role` one re-engagement reminder, ending with “intro channel + DM me to subscribe.” Check the count before confirming. Default max 200 people per send  

**Do not**

- Mass-DM all 5000 people based on “how long since last message”  
- Use interest tags you applied manually for mass promo DMs  
- `@everyone` every day or spam promotions daily  

---

## 5. What AI & Automation Already Do (do not duplicate)

| Automation | Role in activation / subscription | What you keep on |
| --- | --- | --- |
| Daily/weekly summary | Gives people with notifications a reason to open | `DAILY_SUMMARY_*` / `WEEKLY_SUMMARY_*` enabled |
| YouTube new-video digest | Content cadence; brings back old members | `YOUTUBE_MONITOR_ENABLED` enabled |
| Jin10 flash news | Market moves bring people back | `NEWS_FEED_ENABLED` enabled |
| FAQ scheduled push | Reduces “is this community still useful?” doubt | `FAQ_PUSH_ENABLED` enabled |
| RAG `/ask` | When old members finally speak, they get answers in your style | Keep running normally |
| Purchase-intent detection | Someone mentions subscribe/price/trial → product card + **DM notify you** | `INTENT_CONVERT_ENABLED` enabled |
| Welcome drip | New members 24–72h: value → product → reminder | Covers new joins only |
| Opt-in notify DMs | `/promo_notify_panel`, `/dm_role` | Finish Week 0 roles first |

Current CTAs are still “Learn about product” (opens the intro channel) and FAQ. There is **not yet** a “DM owner to subscribe” button — see P0 in the next section.

---

## 6. New Features Needed for the Goal (dev priority)

After Week 0, change the Bot in this order. Without these, people can open the intro channel, but the “route them into your DMs” step stays weak.

### P0 — Align guide buttons with the close path (do first)

Unify every product card (`/signal`, price-inquiry auto-reply, welcome DM, YouTube digest buttons) into two steps:

1. **Learn about product** → open [Subscription intro channel](https://discordapp.com/channels/895349295975370802/923313988996051005) (already uses `SIGNAL_PRODUCT_URL`)  
2. **DM owner to subscribe** → prompt the user to DM you, and send you a lead card (who, which channel, button click vs price question)  

Also add a public `/subscribe` command so people who never ask “how much?” can still click.  
Funnel: intro-page clicks can keep using existing `/signal`; add counts for subscribe-button clicks.

Config suggestion: `SUBSCRIBE_VIA_OWNER_DM=true`. Keep the intro channel URL unchanged.

### P1 — Catch dormant members when they reappear

Someone silent 90 days in target channels who then speaks:

- Reply with a welcome-back line  
- Include “Learn about product / DM owner to subscribe / Claim notify”  

Trigger once per person over a long window. Among ways to wake 5-year members, this beats mass DMs.

### P2 — Owner lead list

- `/leads`: who is recently “Inquiring”, when, and from where  
- `/lead_done @user`: remove Inquiring and record a close (click after you add VIP)  

Otherwise, once inquiries pile up, memory alone will miss deals.

### P3 — Re-engagement DMs to the opt-in list

Already in code ([`FEATURE_LIST.md`](../features/FEATURE_LIST.md) item 62). After Week 0 configures “Event notify” and people claim it, you can use this without waiting for P0.

**Do not:** auto-quote prices for you; mass promo DMs to people who never claimed notify.

---

## 7. Four-Week Execution Calendar

| Timing | Channel owner | Bot / Dev |
| --- | --- | --- |
| Week 0 | Announcement channel, three roles, `.env`, pin panel, re-engagement announcement, three scripts | None (or start P0 in parallel) |
| Week 1 | Clear “Inquiring” daily; keep intro channel a read-only product page | Ship P0: Learn about product + DM owner + `/subscribe` |
| Week 2 | In ops-group channels, `@role` with “this week’s replay + intro link” | Ship P1: dormant reappear welcome-back |
| Weeks 3–4 | `/dm_role` one re-engagement to claimants (confirm count first) | Ship P2: `/leads` `/lead_done` |
| Week 5+ | Keep content cadence; at most one `@everyone` per quarter | Tune copy from `/funnel`; do not stack new promo channels |

---

## 8. How to Tell If Activation & Subscriptions Improved

Do not measure “how many DMs you sent.” Track these weekly (`/funnel days:7` + your own VIP count):

| Metric | Meaning |
| --- | --- |
| People who spoke in channels in 7 days | Were they woken? |
| People who claimed “Event notify” | Is the opt-in list growing? |
| `/signal` count, intro-channel activity | Are people viewing the product page? |
| Purchase-intent count + “Inquiring” headcount | Are people at the checkout door? |
| New VIP you added this week | True subscription rate |

If “Inquiring” is high but VIP does not rise: the bottleneck is your DM reply speed or an unclear intro channel — not missing mass DMs from the Bot.  
If speaking and `/signal` both stay flat: strengthen Week 0 announcements and daily content first; do not add mass promo DMs.

---

## 9. One-Line Division of Labor

- **You:** Make the product page (intro channel) clear, close in DMs, reply to “Inquiring” within 24 hours, decide when to `@everyone`  
- **AI:** Send worth-opening content daily to people still around; when someone asks to buy/price, push the intro page and notify you immediately  
- **New automation:** Make “subscribe” explicitly “DM you”; catch old members the moment they reappear and route them to the intro page; give you a lead list  

Always use this intro channel URL:  
https://discordapp.com/channels/895349295975370802/923313988996051005

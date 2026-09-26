# Growth Trio: Invite Rewards / New-Member Onboarding / 15-Day Read-Only Trial

> Shipped 2026-09-26. Code: `bot/acquisition.py`, `bot/acquisition_cog.py`, `bot/timed_roles.py`, `bot/welcome_flow.py`, `bot/commands.py`. Tests: `tests/test_growth.py`.

The three pieces are independent: invite tracking, the timed-role engine, and the onboarding DM sequence. When the bot lacks privileged permissions it logs a warning and degrades — it never crashes (a permission self-check line is logged at startup).

---

## 1. Invite tracking + leaderboard + rewards

**Member commands**

| Command | Description |
|---|---|
| `/invite` | Generate a personal invite link (ephemeral), with current invite count and reward terms |
| `/invite_leaderboard` | Trailing-30-day Top 10 + your own rank (ephemeral) |
| `/my_invites` | All-time invite count, trailing-30-day rank, ETF reward progress |

**Reward rules (current production config)**

| Condition | Reward | Duration |
|---|---|---|
| ≥ **5** all-time successful invites | **懒人etf🌲** (ETF membership) | 30 days, DM notification; re-earnable 30 days after expiry |
| Monthly Top **5** (trailing 30 days), settled on the 1st | **懒人🌴** (full membership) | 30 days, DM notification |

- Attribution: on `on_member_join` the bot diffs invite `uses` counts against a snapshot and records the inviter. Data lives in `data/invites.json` (`attributions` carry timestamps; `counts` are all-time).
- The leaderboard uses a **trailing-30-day** window; monthly settlement takes the Top N with at least 1 invite. Members holding a paid cohort role (names like `懒人🌴22`) are skipped — they already paid.
- Settlement is idempotent: at most once per month (`data/invite_settlement.json`). If grants fail (e.g. missing permissions) the month is **not** marked settled and the 24h loop retries; already-rewarded winners are not granted twice.

**Config (env vars)**

| Variable | Default | Description |
|---|---|---|
| `INVITE_TRACKING_ENABLED` | `true` | Master switch |
| `INVITE_ETF_REWARD_ROLE_ID` | `1445448090227179711` | Invite reward role (ETF) |
| `INVITE_ETF_MIN_COUNT` | `5` | All-time invites needed for the ETF reward |
| `INVITE_FULL_REWARD_ROLE_ID` | `1445447888439349319` | Monthly TopN reward role (full) |
| `INVITE_TOPN_COUNT` | `5` | Monthly settlement TopN |
| `INVITE_REWARD_DAYS` | `30` | Reward duration (days) |

**Required Discord permissions**: `Manage Server` (list invites), `Manage Roles` (grant/revoke roles), `Create Invite` (`/invite`). The bot's role must sit **above** the reward roles in the role list, or grants fail despite the permission.

---

## 2. New-member onboarding DMs (3 steps)

| When | Content |
|---|---|
| Day 0 (on join) | Welcome + essentials (`#信号说明` channel, `/faq`, `/ask`, `/signal`) + notice of the 15-day read-only trial |
| Day 1 (+24h) | 🎁 Free trial signal (latest value content) |
| Day 3 (+72h) | Paid CTA (product intro + testimonials + purchase buttons) |

- Jobs persist in `data/welcome_drip.json` across restarts; pending jobs are cancelled when a member leaves.
- Blocked DMs (user disabled DMs) are logged only — no retries, no nagging.

**Config**

| Variable | Default | Description |
|---|---|---|
| `WELCOME_FLOW_ENABLED` | `false` | Master switch (recommended on) |
| `ONBOARD_DAY1_DELAY_SECONDS` | `86400` | Day-1 delay (seconds) |
| `ONBOARD_DAY3_DELAY_SECONDS` | `259200` | Day-3 delay (seconds) |

---

## 3. 15-day read-only trial for new members

- On join, a new member gets the **`新人体验15天`** role (auto-created at startup) plus a timed-grant record (`data/timed_roles.json`).
- The role gets **read-only** access to member channels (default: fullversion + ETF squads): `view_channel=True, send_messages=False` (idempotent).
- **Auto-revoked after 15 days** (checked every 5 minutes). Paid cohort roles are protected: roles matching `^懒人.*\d` are never removed by the expiry sweep (logged when skipped).
- Members who already hold a paid role don't get the trial role.
- When a member leaves, open grants are marked cancelled (kept for audit).

**Config**

| Variable | Default | Description |
|---|---|---|
| `TRIAL_ROLE_NAME` | `新人体验15天` | Trial role name (renaming creates a new role — don't change lightly) |
| `TRIAL_MEMBER_CHANNEL_IDS` | `912366231112282172,923449257711763466` | Member channels in the trial |
| `TRIAL_GRANT_DAYS` | `15` | Trial duration (days) |

---

## Ops notes

1. **Permissions**: `Manage Server` + `Manage Roles` are required; the bot role must rank above `懒人etf🌲` / `懒人🌴` / `新人体验15天`.
2. **Rule changes need no code**: thresholds, TopN, durations, and delays are all env vars.
3. **Data files** (don't hand-edit; don't commit dirty copies): `data/invites.json`, `data/timed_roles.json`, `data/invite_settlement.json`, `data/welcome_drip.json`.
4. **Known limits**: the leaderboard window is trailing 30 days while `counts` are all-time; `attributions` keeps only the latest 500 entries (the leaderboard window shrinks past that volume).

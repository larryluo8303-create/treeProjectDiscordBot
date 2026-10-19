"""Tests for acquisition: purchase intent, funnel stats, drip jobs, invite attribution."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestPurchaseIntent:
    def test_matches_subscribe_and_price(self):
        from bot.acquisition import is_purchase_intent
        assert is_purchase_intent("怎么订阅 BigTreeSignal")
        assert is_purchase_intent("试用多少钱")
        assert is_purchase_intent("VIP 怎么开通")
        assert is_purchase_intent("How much is the subscription")

    def test_ignores_live_signal_questions(self):
        from bot.acquisition import is_purchase_intent
        assert is_purchase_intent("今天QQQ有没有买点信号") == []
        assert is_purchase_intent("现在能买吗") == []
        assert is_purchase_intent("") == []

    def test_dedupes_matches(self):
        from bot.acquisition import is_purchase_intent
        hits = is_purchase_intent("订阅订阅试用")
        assert len(hits) == len(set(h.lower() for h in hits))


class TestValidCtaUrl:
    def test_rejects_placeholder_and_empty(self):
        from bot.acquisition import is_valid_cta_url
        assert is_valid_cta_url("") is False
        assert is_valid_cta_url("https://your-product-url.com") is False
        assert is_valid_cta_url("https://bigtreesignal.com/join") is True


class TestFunnel:
    def test_record_and_snapshot(self, tmp_path):
        funnel_file = tmp_path / "funnel.json"
        with patch("bot.acquisition.FUNNEL_FILE", str(funnel_file)):
            from bot.acquisition import funnel_snapshot, record_funnel
            record_funnel("joins")
            record_funnel("joins")
            record_funnel("intent_hits")
            snap = funnel_snapshot(7)
            assert snap["lifetime"]["joins"] == 2
            assert snap["window"]["joins"] == 2
            assert snap["window"]["intent_hits"] == 1

    def test_unknown_metric_is_ignored(self, tmp_path):
        funnel_file = tmp_path / "funnel.json"
        with patch("bot.acquisition.FUNNEL_FILE", str(funnel_file)):
            from bot.acquisition import funnel_snapshot, record_funnel
            record_funnel("not_a_metric")
            snap = funnel_snapshot(1)
            assert snap["lifetime"]["joins"] == 0


class TestWelcomeDrip:
    def test_schedule_and_due(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.ONBOARD_DAY1_DELAY_SECONDS", 0), \
             patch("bot.acquisition.ONBOARD_DAY3_DELAY_SECONDS", 99999):
            from bot.acquisition import due_drip_jobs, mark_drip_sent, schedule_welcome_drip
            # delay 0 skips that step
            created = schedule_welcome_drip(111, 222)
            assert len(created) == 1
            assert created[0]["step"] == "cta"
            due = due_drip_jobs(datetime.now(timezone.utc) + timedelta(days=2))
            assert {j["step"] for j in due} == {"cta"}
            mark_drip_sent(created[0]["id"])
            due2 = due_drip_jobs(datetime.now(timezone.utc) + timedelta(days=2))
            assert created[0]["id"] not in {j["id"] for j in due2}

    def test_cancel_user_jobs(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.ONBOARD_DAY1_DELAY_SECONDS", 10), \
             patch("bot.acquisition.ONBOARD_DAY3_DELAY_SECONDS", 20):
            from bot.acquisition import cancel_drip_for_user, due_drip_jobs, schedule_welcome_drip
            schedule_welcome_drip(1, 99)
            assert cancel_drip_for_user(1) == 2
            assert due_drip_jobs(datetime.now(timezone.utc) + timedelta(days=1)) == []


class TestInviteAttribution:
    def test_unique_increased_code(self):
        from bot.acquisition import diff_invite_attribution
        prev = {"abc": {"uses": 1, "inviter_id": 10}}
        cur = {"abc": {"uses": 2, "inviter_id": 10}}
        assert diff_invite_attribution(prev, cur) == ("abc", 10)

    def test_ambiguous_when_two_codes_increase(self):
        from bot.acquisition import diff_invite_attribution
        prev = {"a": {"uses": 1, "inviter_id": 1}, "b": {"uses": 1, "inviter_id": 2}}
        cur = {"a": {"uses": 2, "inviter_id": 1}, "b": {"uses": 2, "inviter_id": 2}}
        assert diff_invite_attribution(prev, cur) is None

    def test_new_code_with_uses(self):
        from bot.acquisition import diff_invite_attribution
        prev = {}
        cur = {"xyz": {"uses": 1, "inviter_id": 42}}
        assert diff_invite_attribution(prev, cur) == ("xyz", 42)

    def test_record_invite_join_increments_count(self, tmp_path):
        invites_file = tmp_path / "invites.json"
        funnel_file = tmp_path / "funnel.json"
        with patch("bot.acquisition.INVITES_FILE", str(invites_file)), \
             patch("bot.acquisition.FUNNEL_FILE", str(funnel_file)):
            from bot.acquisition import invite_count_for, record_invite_join
            assert record_invite_join("abc", 10, 99, 1) == 1
            assert record_invite_join("abc", 10, 100, 1) == 2
            assert invite_count_for(10) == 2

    def test_reward_threshold(self):
        from bot.acquisition import should_grant_invite_reward
        with patch("bot.acquisition.INVITE_REWARD_THRESHOLD", 3), \
             patch("bot.acquisition.INVITE_REWARD_ROLE_ID", 555):
            assert should_grant_invite_reward(2) is False
            assert should_grant_invite_reward(3) is True


class TestRestCtaComponents:
    def test_empty_without_real_urls(self):
        from bot.acquisition import rest_cta_components
        with patch("bot.acquisition.SIGNAL_PRODUCT_URL", "https://your-product-url.com"), \
             patch("bot.acquisition.FREE_TRIAL_ENABLED", False):
            assert rest_cta_components() == []

    def test_includes_product_link(self):
        from bot.acquisition import rest_cta_components
        with patch("bot.acquisition.SIGNAL_PRODUCT_URL", "https://example.com/signal"), \
             patch("bot.acquisition.FREE_TRIAL_ENABLED", False):
            rows = rest_cta_components()
            assert rows[0]["components"][0]["url"] == "https://example.com/signal"


_TIERS = [
    {"invites": 10, "days": 30, "role": "etf"},
    {"invites": 30, "days": 90, "role": "etf"},
    {"invites": 100, "days": 365, "role": "full"},
]


def _ambassador_patches(tmp_path, monkeypatch):
    """Point grant/invite state at tmp files and pin role ids."""
    timed_roles_file = tmp_path / "timed_roles.json"
    invites_file = tmp_path / "invites.json"
    monkeypatch.setattr("bot.timed_roles.TIMED_ROLES_FILE", str(timed_roles_file))
    monkeypatch.setattr("bot.acquisition.INVITES_FILE", str(invites_file))
    monkeypatch.setattr("bot.acquisition.INVITE_ETF_REWARD_ROLE_ID", 111)
    monkeypatch.setattr("bot.acquisition.INVITE_FULL_REWARD_ROLE_ID", 222)
    monkeypatch.setattr("bot.config.AMBASSADOR_TIERS", [dict(t) for t in _TIERS])
    monkeypatch.setattr("bot.config.AMBASSADOR_COOLDOWN_DAYS", 30)


def _write_grant(tmp_path, user_id, role_id, reason, days_ago, count_at_grant):
    import json
    from datetime import datetime, timedelta, timezone

    granted = datetime.now(timezone.utc) - timedelta(days=days_ago)
    grants = [{
        "user_id": user_id,
        "guild_id": 1,
        "role_id": role_id,
        "reason": reason,
        "days": 30,
        "granted_at": granted.isoformat(),
        "expires_at": (granted + timedelta(days=30)).isoformat(),
        "revoked": False,
        "meta": {"count_at_grant": count_at_grant},
    }]
    (tmp_path / "timed_roles.json").write_text(json.dumps(grants), encoding="utf-8")


class TestAmbassadorTiers:
    def test_due_at_threshold(self, tmp_path, monkeypatch):
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_due_tiers
        due = ambassador_due_tiers(10, 10)
        assert [t["invites"] for t in due] == [10]

    def test_not_due_below_threshold(self, tmp_path, monkeypatch):
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_due_tiers
        assert ambassador_due_tiers(10, 9) == []

    def test_cooldown_blocks_refire(self, tmp_path, monkeypatch):
        """Same tier re-earned too soon (10 days < 30-day cooldown) -> blocked."""
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_due_tiers
        _write_grant(tmp_path, 10, 111, "ambassador_10", days_ago=10, count_at_grant=10)
        # 20 verified: marginal 20-10=10 >= threshold, but cooldown not elapsed
        assert ambassador_due_tiers(10, 20) == []

    def test_refire_after_cooldown_with_new_invites(self, tmp_path, monkeypatch):
        """Same tier with a fresh batch of invites after cooldown -> due again."""
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_due_tiers
        _write_grant(tmp_path, 10, 111, "ambassador_10", days_ago=40, count_at_grant=10)
        due = ambassador_due_tiers(10, 20)
        assert [t["invites"] for t in due] == [10]

    def test_upgrade_to_higher_tier(self, tmp_path, monkeypatch):
        """Reaching 35: tier 30 becomes due (tier 10 also re-due on its own marginal)."""
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_due_tiers
        _write_grant(tmp_path, 10, 111, "ambassador_10", days_ago=40, count_at_grant=10)
        due = ambassador_due_tiers(10, 35)
        assert sorted(t["invites"] for t in due) == [10, 30]

    def test_higher_tier_independent_baseline(self, tmp_path, monkeypatch):
        """Tier 30 uses its own baseline (never granted -> 0), not tier 10's."""
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_due_tiers
        due = ambassador_due_tiers(10, 35)
        assert 30 in [t["invites"] for t in due]

    def test_role_resolution(self, tmp_path, monkeypatch):
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_role_id
        assert ambassador_role_id({"invites": 10, "days": 30, "role": "etf"}) == 111
        assert ambassador_role_id({"invites": 100, "days": 365, "role": "full"}) == 222

    def test_progress_report(self, tmp_path, monkeypatch):
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import ambassador_progress, next_ambassador_tier_gap
        _write_grant(tmp_path, 10, 111, "ambassador_10", days_ago=40, count_at_grant=10)
        prog = ambassador_progress(10, 17)
        by_invites = {p["invites"]: p for p in prog}
        assert by_invites[10]["marginal"] == 7
        assert by_invites[10]["last_granted_at"] != ""
        assert by_invites[30]["last_granted_at"] == ""
        gap = next_ambassador_tier_gap(10, 17)
        assert gap == (10, 3)  # marginal 7 of 10 -> 3 missing

    def test_gap_skips_tier_claimed_within_cooldown(self, tmp_path, monkeypatch):
        """刚领过 10 人档（冷却期内）："下一档"应是 30 人档，而非从 0 重攒 10 人档。"""
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import next_ambassador_tier_gap
        _write_grant(tmp_path, 10, 111, "ambassador_10", days_ago=0, count_at_grant=15)
        gap = next_ambassador_tier_gap(10, 15)
        assert gap == (30, 15)  # 30 人档进度 15/30，还差 15 人

    def test_gap_none_when_all_tiers_in_cooldown(self, tmp_path, monkeypatch):
        """所有档位都在冷却期内：无下一档可追，返回 None。"""
        _ambassador_patches(tmp_path, monkeypatch)
        from bot.acquisition import next_ambassador_tier_gap
        _write_grant(tmp_path, 10, 111, "ambassador_10", days_ago=0, count_at_grant=15)
        import json
        from datetime import datetime, timedelta, timezone
        granted = datetime.now(timezone.utc)
        grants = json.loads((tmp_path / "timed_roles.json").read_text(encoding="utf-8"))
        grants += [
            {"user_id": 10, "guild_id": 1, "role_id": 111, "reason": "ambassador_30",
             "days": 90, "granted_at": granted.isoformat(),
             "expires_at": (granted + timedelta(days=90)).isoformat(),
             "revoked": False, "meta": {"count_at_grant": 30}},
            {"user_id": 10, "guild_id": 1, "role_id": 222, "reason": "ambassador_100",
             "days": 365, "granted_at": granted.isoformat(),
             "expires_at": (granted + timedelta(days=365)).isoformat(),
             "revoked": False, "meta": {"count_at_grant": 100}},
        ]
        (tmp_path / "timed_roles.json").write_text(json.dumps(grants), encoding="utf-8")
        assert next_ambassador_tier_gap(10, 100) is None

    def test_env_override_parsing(self, monkeypatch):
        from bot.config import _parse_ambassador_tiers
        tiers = _parse_ambassador_tiers('[{"invites":5,"days":7,"role":"etf"}]')
        assert tiers == [{"invites": 5, "days": 7, "role": "etf"}]
        assert _parse_ambassador_tiers("not json") == _TIERS
        assert _parse_ambassador_tiers("") == _TIERS
        # invalid entries are filtered out
        tiers = _parse_ambassador_tiers('[{"invites":5,"days":7,"role":"bogus"},{"invites":20,"days":60,"role":"full"}]')
        assert tiers == [{"invites": 20, "days": 60, "role": "full"}]

    async def test_verified_count_excludes_left_members(self, tmp_path, monkeypatch):
        """防刷：已退群的受邀人不计入。"""
        import json
        _ambassador_patches(tmp_path, monkeypatch)
        (tmp_path / "invites.json").write_text(json.dumps({
            "codes": {},
            "counts": {"10": 2},
            "attributions": [
                {"code": "a", "inviter_id": 10, "joiner_id": 101, "guild_id": 1,
                 "ts": "2026-10-01T00:00:00+00:00"},
                {"code": "a", "inviter_id": 10, "joiner_id": 102, "guild_id": 1,
                 "ts": "2026-10-02T00:00:00+00:00"},
            ],
        }), encoding="utf-8")

        class FakeGuild:
            def get_member(self, uid):
                return object() if uid == 101 else None

            async def fetch_member(self, uid):
                raise Exception("not found")

        from bot.acquisition import verified_invite_count
        assert await verified_invite_count(FakeGuild(), 10) == 1

    async def test_grant_records_count_at_grant(self, tmp_path, monkeypatch):
        """grant_timed_role persists meta so the next marginal check is exact."""
        _ambassador_patches(tmp_path, monkeypatch)

        class FakeRole:
            id = 111

        class FakeMember:
            id = 10
            roles = []

            async def add_roles(self, role, reason=None):
                self.roles.append(role)

        class FakeGuild:
            id = 1

            def get_role(self, rid):
                return FakeRole() if rid == 111 else None

            def get_member(self, uid):
                return FakeMember() if uid == 10 else None

        class FakeBot:
            def get_guild(self, gid):
                return FakeGuild() if gid == 1 else None

        from bot.timed_roles import grant_timed_role, last_grant, supersede_grants
        ok = await grant_timed_role(
            FakeBot(), 10, 1, 111, 30, "ambassador_10",
            meta={"count_at_grant": 12},
        )
        assert ok is True
        last = last_grant(10, 111, reason="ambassador_10")
        assert last is not None
        assert last.get("meta") == {"count_at_grant": 12}
        # Superseding retires the record without touching Discord state here.
        assert supersede_grants(10, 111, note="test") == 1
        assert last_grant(10, 111, reason="ambassador_10")["revoked"] is True

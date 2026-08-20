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
             patch("bot.acquisition.WELCOME_VALUE_DELAY_SECONDS", 0), \
             patch("bot.acquisition.WELCOME_CTA_DELAY_SECONDS", 99999), \
             patch("bot.acquisition.WELCOME_REMINDER_DELAY_SECONDS", 99999):
            from bot.acquisition import due_drip_jobs, mark_drip_sent, schedule_welcome_drip
            # delay 0 skips that step
            created = schedule_welcome_drip(111, 222)
            assert len(created) == 2
            due = due_drip_jobs(datetime.now(timezone.utc) + timedelta(days=2))
            assert {j["step"] for j in due} == {"cta", "reminder"}
            mark_drip_sent(created[0]["id"])
            due2 = due_drip_jobs(datetime.now(timezone.utc) + timedelta(days=2))
            assert created[0]["id"] not in {j["id"] for j in due2}

    def test_cancel_user_jobs(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.WELCOME_VALUE_DELAY_SECONDS", 10), \
             patch("bot.acquisition.WELCOME_CTA_DELAY_SECONDS", 20), \
             patch("bot.acquisition.WELCOME_REMINDER_DELAY_SECONDS", 30):
            from bot.acquisition import cancel_drip_for_user, due_drip_jobs, schedule_welcome_drip
            schedule_welcome_drip(1, 99)
            assert cancel_drip_for_user(1) == 3
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

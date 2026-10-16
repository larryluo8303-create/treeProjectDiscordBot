"""Portfolio diagnosis tool — /持仓诊断 slash command.

Members input holdings like "NVDA:30,TSLA:20,AAPL:50" (ticker:weight%).
The bot fetches 6-month daily closes from Yahoo, computes concentration
(HHI), correlation, annualized volatility, sector breakdown, then asks the
LLM for a structured Chinese diagnosis. Analysis only — no buy/sell advice.

Replies are ephemeral: only the requesting member sees their holdings.
"""

import asyncio
import logging
import math
import re
from datetime import datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import LLM_MODEL

logger = logging.getLogger(__name__)

_SECTOR_MAP = {
    "NVDA": "半导体", "AMD": "半导体", "AVGO": "半导体", "MU": "半导体",
    "INTC": "半导体", "TSM": "半导体", "QCOM": "半导体", "ARM": "半导体",
    "AAPL": "消费电子", "MSFT": "软件/云", "GOOGL": "软件/云", "AMZN": "电商/云",
    "META": "社交/广告", "TSLA": "电动车", "NFLX": "流媒体",
    "COIN": "加密", "MSTR": "加密", "MARA": "加密", "RIOT": "加密",
    "JPM": "金融", "BAC": "金融", "V": "金融", "MA": "金融",
    "XOM": "能源", "CVX": "能源",
    "LLY": "医药", "UNH": "医药", "JNJ": "医药",
    "SPY": "宽基ETF", "QQQ": "宽基ETF", "DIA": "宽基ETF", "IWM": "宽基ETF",
    "TLT": "债券ETF", "GLD": "黄金ETF",
}

_ENTRY_RE = re.compile(r"^\s*([A-Za-z.\-]{1,8})\s*:\s*(\d+(?:\.\d+)?)\s*$")


def parse_holdings(text: str) -> list[tuple[str, float]] | str:
    """Parse 'NVDA:30,TSLA:20' -> [(ticker, weight)] or an error message."""
    if not text or not text.strip():
        return "请输入持仓，格式如：NVDA:30,TSLA:20,AAPL:50（代码:权重%）"
    parts = re.split(r"[,，\s]+", text.strip())
    out: list[tuple[str, float]] = []
    seen = set()
    for p in parts:
        if not p:
            continue
        m = _ENTRY_RE.match(p)
        if not m:
            return f"无法识别「{p}」，请用 代码:权重% 的格式，例如 NVDA:30,TSLA:20"
        ticker = m.group(1).upper()
        weight = float(m.group(2))
        if weight <= 0:
            return f"「{ticker}」的权重必须大于 0"
        if ticker in seen:
            return f"「{ticker}」出现了两次，请合并权重"
        seen.add(ticker)
        out.append((ticker, weight))
    if len(out) < 2:
        return "至少输入 2 只持仓才能做诊断"
    if len(out) > 10:
        return "最多支持 10 只持仓"
    total = sum(w for _, w in out)
    return [(t, w / total) for t, w in out]


async def fetch_daily_closes(session: aiohttp.ClientSession, ticker: str) -> list[float] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=6mo"
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json(content_type=None)
    except Exception as exc:
        logger.warning("Portfolio: fetch failed for %s: %s", ticker, exc)
        return None
    try:
        result = payload["chart"]["result"][0]
        # Prefer split/dividend-adjusted closes so long-window returns aren't distorted.
        adj = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose") or []
        adj = [c for c in adj if c]
        if len(adj) >= 60:
            return adj
        closes = result["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c]
        return closes if len(closes) >= 60 else None
    except (KeyError, IndexError, TypeError):
        return None


def _log_returns(closes: list[float]) -> list[float]:
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _corr(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    ma, mb = _mean(a), _mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def compute_metrics(holdings: list[tuple[str, float]], series: dict[str, list[float]]) -> dict:
    tickers = [t for t, _ in holdings]
    weights = [w for _, w in holdings]
    rets = {t: _log_returns(series[t]) for t in tickers}
    n = min(len(r) for r in rets.values())
    rets = {t: r[-n:] for t, r in rets.items()}

    # HHI concentration (0-10000 scale)
    hhi = sum((w * 100) ** 2 for w in weights)

    # Average pairwise correlation
    corrs = []
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            corrs.append(_corr(rets[tickers[i]], rets[tickers[j]]))
    avg_corr = _mean(corrs) if corrs else 0.0

    # Portfolio annualized volatility
    means = {t: _mean(rets[t]) for t in tickers}
    port_rets = [
        sum(weights[k] * (rets[tickers[k]][i] - means[tickers[k]]) for k in range(len(tickers)))
        for i in range(n)
    ]
    port_var = sum(r * r for r in port_rets) / (n - 1)
    ann_vol = math.sqrt(port_var * 252) * 100

    # 6-month weighted return
    six_mo = sum(weights[k] * (series[tickers[k]][-1] / series[tickers[k]][0] - 1) for k in range(len(tickers))) * 100

    # Sector breakdown
    sectors: dict[str, float] = {}
    for t, w in holdings:
        s = _SECTOR_MAP.get(t, "其他")
        sectors[s] = sectors.get(s, 0.0) + w

    return {
        "hhi": hhi,
        "avg_corr": avg_corr,
        "ann_vol": ann_vol,
        "six_mo_ret": six_mo,
        "max_weight": max(weights) * 100,
        "sectors": sectors,
    }


def _metrics_text(holdings: list[tuple[str, float]], m: dict) -> str:
    lines = [f"{t}: {w*100:.1f}%" for t, w in holdings]
    sector_txt = "、".join(f"{s} {w*100:.0f}%" for s, w in sorted(m["sectors"].items(), key=lambda x: -x[1]))
    return (
        "持仓：" + "，".join(lines) + "\n"
        f"集中度 HHI：{m['hhi']:.0f}（<1500 分散，1500-2500 适中，>2500 集中）\n"
        f"最大单只权重：{m['max_weight']:.1f}%\n"
        f"平均两两相关性：{m['avg_corr']:.2f}\n"
        f"组合年化波动率：{m['ann_vol']:.1f}%\n"
        f"近6个月组合回报：{m['six_mo_ret']:+.1f}%\n"
        f"行业分布：{sector_txt}"
    )


_DIAGNOSE_PROMPT = """你是一位组合分析助手。根据以下持仓的量化指标，用中文给出结构化诊断（300字以内）。

要求：
1. 分点评价：集中度风险、相关性（是否同涨同跌）、波动率水平、行业偏向。
2. 用一句话总结这个组合的风格倾向（偏进攻/偏防御/偏集中/偏分散）。
3. 可以指出 1-2 个值得注意的风险点。
4. 严禁给出任何买卖建议、调仓建议或具体操作指令；只做客观分析。
5. 结尾必须加一句：「以上分析基于历史数据和公开信息，仅供参考，不构成投资建议。」

量化指标：
{metrics}
"""


class PortfolioCog(commands.Cog):
    """Portfolio diagnosis tool: /持仓诊断."""

    def __init__(self, bot: commands.Bot, openai_client) -> None:
        self.bot = bot
        self.openai_client = openai_client

    @app_commands.command(name="持仓诊断", description="输入持仓生成组合诊断（仅自己可见）")
    @app_commands.describe(持仓="格式如 NVDA:30,TSLA:20,AAPL:50（代码:权重%）")
    async def diagnose(self, interaction: discord.Interaction, 持仓: str) -> None:
        parsed = parse_holdings(持仓)
        if isinstance(parsed, str):
            await interaction.response.send_message(parsed, ephemeral=True)
            return
        holdings = parsed
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                results = await asyncio.gather(
                    *(fetch_daily_closes(session, t) for t, _ in holdings)
                )
            series = {}
            missing = []
            for (t, _), closes in zip(holdings, results):
                if closes:
                    series[t] = closes
                else:
                    missing.append(t)
            if missing:
                await interaction.followup.send(
                    f"以下代码拉不到行情数据，请检查代码是否正确：{', '.join(missing)}",
                    ephemeral=True,
                )
                return
            metrics = compute_metrics(holdings, series)
            metrics_txt = _metrics_text(holdings, metrics)
            diagnosis = ""
            if self.openai_client is not None:
                try:
                    resp = await self.openai_client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=[{"role": "user", "content": _DIAGNOSE_PROMPT.format(metrics=metrics_txt)}],
                        max_tokens=600,
                        temperature=0.3,
                    )
                    diagnosis = (resp.choices[0].message.content or "").strip()
                except Exception as exc:
                    logger.warning("Portfolio: LLM diagnosis failed: %s", exc)
            if not diagnosis:
                diagnosis = "AI 诊断暂时不可用，以下是量化指标供参考。\n以上分析基于历史数据和公开信息，仅供参考，不构成投资建议。"
            await interaction.followup.send(
                f"📊 **持仓诊断**（{_datetime_now()})\n\n{diagnosis}",
                ephemeral=True,
            )
        except Exception as exc:
            logger.warning("Portfolio: diagnose failed: %s", exc)
            await interaction.followup.send("诊断失败，请稍后再试。", ephemeral=True)


def _datetime_now() -> str:
    return datetime.now().strftime("%Y-%m-%d")

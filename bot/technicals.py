"""On-demand market data commands — pure indicator display, no conclusions.

- /技术面 <代码>: RSI(14), MACD, MA20/50/200 position, volume vs 20-day avg
- /报价 <代码>: last price, day change, OHLC, volume, pre/post-market price

Both replies are ephemeral (visible only to the requester) and always end with
a not-investment-advice disclaimer. No buy/sell signals, no price targets.
"""

import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.earnings import _CN_NAMES

logger = logging.getLogger(__name__)

_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_DISCLAIMER = "以上为公开行情数据的客观指标展示，仅供参考，不构成投资建议。"


def _ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _macd(closes: list[float]) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (dif, dea, hist, prev_hist). prev_hist lets callers tell a fresh
    crossover (金叉/死叉) apart from merely staying above/below."""
    if len(closes) < 35:
        return None, None, None, None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif_line = [a - b for a, b in zip(ema12, ema26)]
    dea_line = _ema(dif_line, 9)
    hist = dif_line[-1] - dea_line[-1]
    prev_hist = dif_line[-2] - dea_line[-2]
    return dif_line[-1], dea_line[-1], hist, prev_hist


def _rsi_label(rsi: float) -> str:
    if rsi >= 70:
        return "超买区"
    if rsi >= 55:
        return "偏强"
    if rsi > 45:
        return "中性"
    if rsi > 30:
        return "偏弱"
    return "超卖区"


async def _fetch_daily(session: aiohttp.ClientSession, ticker: str) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
    try:
        async with session.get(url, headers=_YAHOO_HEADERS, timeout=25) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json(content_type=None)
            result = payload["chart"]["result"][0]
            q = result["indicators"]["quote"][0]
            # Filter rows with a null close, keeping OHLCV aligned — Yahoo
            # occasionally returns null closes (e.g. partial bars); dropping
            # them from closes only would misalign vols/open/high/low.
            bars = [
                (c, o, h, l, v or 0)
                for c, o, h, l, v in zip(
                    q["close"], q["open"], q["high"], q["low"], q["volume"]
                )
                if c
            ]
            if len(bars) < 60:
                return None
            closes = [b[0] for b in bars]
            return {
                "meta": result["meta"],
                "closes": closes,
                "opens": [b[1] or 0 for b in bars],
                "highs": [b[2] or 0 for b in bars],
                "lows": [b[3] or 0 for b in bars],
                "vols": [b[4] for b in bars],
            }
    except Exception as exc:
        logger.warning("Technicals: fetch failed for %s: %s", ticker, exc)
        return None


def _fmt_vol(v: float) -> str:
    if v >= 1e9:
        return f"{v / 1e9:.2f}亿"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    return f"{v:,.0f}"


class TechnicalsCog(commands.Cog):
    """Ephemeral market-data commands."""

    def __init__(self, bot: commands.Bot, openai_client=None) -> None:
        self.bot = bot

    @app_commands.command(name="技术面", description="查看个股技术指标速览（RSI/MACD/均线/量能）")
    @app_commands.describe(代码="股票代码，如 NVDA")
    async def technicals(self, interaction: discord.Interaction, 代码: str):
        await interaction.response.defer(ephemeral=True)
        ticker = 代码.strip().upper()
        if not ticker or len(ticker) > 10:
            await interaction.followup.send("请输入有效的股票代码，如 `NVDA`。", ephemeral=True)
            return
        async with aiohttp.ClientSession(trust_env=True) as session:
            data = await _fetch_daily(session, ticker)
        if not data:
            await interaction.followup.send(f"未找到 {ticker} 的行情数据，请检查代码。", ephemeral=True)
            return
        closes = data["closes"]
        vols = data["vols"]
        price = closes[-1]
        cn = _CN_NAMES.get(ticker, "")

        rsi = _rsi(closes)
        dif, dea, hist, prev_hist = _macd(closes)
        ma20 = sum(closes[-20:]) / 20
        ma50 = sum(closes[-50:]) / 50
        ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
        vol_ratio = (vols[-1] / (sum(vols[-21:-1]) / 20)) if sum(vols[-21:-1]) else 0

        pos = []
        pos.append(f"MA20 ${ma20:.2f}（{'上' if price >= ma20 else '下'}）")
        pos.append(f"MA50 ${ma50:.2f}（{'上' if price >= ma50 else '下'}）")
        if ma200:
            pos.append(f"MA200 ${ma200:.2f}（{'上' if price >= ma200 else '下'}）")

        rsi_txt = f"{rsi:.1f}（{_rsi_label(rsi)}）" if rsi is not None else "数据不足"
        if dif is None:
            macd_txt = "数据不足"
        else:
            if hist > 0 and prev_hist <= 0:
                cross = "金叉（刚形成）"
            elif hist < 0 and prev_hist >= 0:
                cross = "死叉（刚形成）"
            elif hist > 0:
                cross = "DIF 在 DEA 上方"
            elif hist < 0:
                cross = "DIF 在 DEA 下方"
            else:
                cross = "粘合"
            macd_txt = f"DIF {dif:.2f} / DEA {dea:.2f}，{cross}"

        msg = (
            f"📊 **技术面速览**：{cn + ' ' if cn else ''}({ticker}) ${price:.2f}\n"
            f"• RSI(14)：{rsi_txt}\n"
            f"• MACD：{macd_txt}\n"
            f"• 均线位置：{'、'.join(pos)}\n"
            f"• 量能：最新成交量约为 20 日均量的 {vol_ratio:.1f}x\n"
            f"{_DISCLAIMER}"
        )
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="报价", description="快速查看个股最新报价（含盘前盘后）")
    @app_commands.describe(代码="股票代码，如 NVDA")
    async def quote(self, interaction: discord.Interaction, 代码: str):
        await interaction.response.defer(ephemeral=True)
        ticker = 代码.strip().upper()
        if not ticker or len(ticker) > 10:
            await interaction.followup.send("请输入有效的股票代码，如 `NVDA`。", ephemeral=True)
            return
        async with aiohttp.ClientSession(trust_env=True) as session:
            data = await _fetch_daily(session, ticker)
        if not data:
            await interaction.followup.send(f"未找到 {ticker} 的行情数据，请检查代码。", ephemeral=True)
            return
        meta = data["meta"]
        closes = data["closes"]
        price = meta.get("regularMarketPrice") or closes[-1]
        prev = meta.get("chartPreviousClose") or closes[-2]
        pct = (price - prev) / prev * 100 if prev else 0
        cn = _CN_NAMES.get(ticker, "")
        arrow = "🔺" if pct > 0 else "🔻" if pct < 0 else "➖"

        q = data
        o = q["opens"][-1]
        h = q["highs"][-1]
        l = q["lows"][-1]
        v = q["vols"][-1]

        ext_lines = []
        pre = meta.get("preMarketPrice")
        post = meta.get("postMarketPrice")
        if pre:
            ext_lines.append(f"盘前 ${pre:.2f}（{(pre - prev) / prev * 100:+.1f}%）")
        if post:
            ext_lines.append(f"盘后 ${post:.2f}（{(post - prev) / prev * 100:+.1f}%）")
        ext_txt = "\n" + "\n".join(f"• {e}" for e in ext_lines) if ext_lines else ""

        msg = (
            f"💹 **报价**：{cn + ' ' if cn else ''}({ticker})\n"
            f"• 现价 ${price:.2f} {arrow} {pct:+.2f}%（相对昨收 ${prev:.2f}）\n"
            f"• 今开 ${o:.2f} / 最高 ${h:.2f} / 最低 ${l:.2f} / 成交量 {_fmt_vol(v)}"
            f"{ext_txt}\n"
            f"{_DISCLAIMER}"
        )
        await interaction.followup.send(msg, ephemeral=True)

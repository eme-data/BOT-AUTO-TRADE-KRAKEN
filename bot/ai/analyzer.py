"""Claude AI analyzer – validates trading signals with LLM intelligence."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import structlog

from bot.ai.models import (
    AIAnalysisRequest,
    AIAnalysisResult,
    AIVerdict,
    AnalysisMode,
)
from bot.ai.prompts import (
    MARKET_REVIEW_PROMPT,
    POST_TRADE_PROMPT,
    PRE_TRADE_PROMPT,
    SENTIMENT_PROMPT,
    SYSTEM_PROMPT,
)
from bot.config import settings

logger = structlog.get_logger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Prompt templates per mode
_PROMPT_MAP = {
    AnalysisMode.PRE_TRADE: PRE_TRADE_PROMPT,
    AnalysisMode.MARKET_REVIEW: MARKET_REVIEW_PROMPT,
    AnalysisMode.SENTIMENT: SENTIMENT_PROMPT,
    AnalysisMode.POST_TRADE: POST_TRADE_PROMPT,
}


class ClaudeAnalyzer:
    """Sends analysis requests to Claude API and parses structured responses."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def is_enabled(self) -> bool:
        return bool(
            settings.ai_enabled
            and settings.ai_api_key
        )

    @property
    def _api_key(self) -> str:
        return settings.ai_api_key

    @property
    def _model(self) -> str:
        return settings.ai_model

    @property
    def _max_tokens(self) -> int:
        return settings.ai_max_tokens

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Main entry point ───────────────────────────────

    async def analyze(self, request: AIAnalysisRequest) -> AIAnalysisResult:
        """Run a Claude analysis. Returns result with verdict + reasoning."""
        if not self.is_enabled:
            return AIAnalysisResult(
                verdict=AIVerdict.APPROVE,
                confidence=0.0,
                reasoning="AI analysis disabled",
            )

        # Check if this analysis mode is enabled
        if not self._is_mode_enabled(request.mode):
            return AIAnalysisResult(
                verdict=AIVerdict.APPROVE,
                confidence=0.0,
                reasoning=f"AI mode '{request.mode.value}' disabled",
            )

        # Build prompt
        prompt = self._build_prompt(request)

        # Call Claude API
        t0 = time.monotonic()
        try:
            raw_response = await self._call_claude(prompt)
            latency_ms = int((time.monotonic() - t0) * 1000)
        except Exception as exc:
            logger.error("ai_call_error", error=str(exc))
            # On error, default to APPROVE (don't block trading)
            return AIAnalysisResult(
                verdict=AIVerdict.APPROVE,
                confidence=0.0,
                reasoning=f"AI analysis error: {exc}",
            )

        # Parse response
        result = self._parse_response(raw_response, latency_ms)

        logger.info(
            "ai_analysis_done",
            pair=request.pair,
            mode=request.mode.value,
            verdict=result.verdict.value,
            confidence=result.confidence,
            latency_ms=latency_ms,
        )

        return result

    # ── Pre-trade convenience method ───────────────────

    async def validate_signal(
        self,
        pair: str,
        direction: str,
        strategy: str,
        confidence: float,
        indicators: dict[str, Any],
        recent_bars: list[dict[str, float]],
        open_positions: list[dict[str, Any]],
        account_balance: float,
    ) -> AIAnalysisResult:
        """Convenience: validate a trading signal before execution."""
        request = AIAnalysisRequest(
            mode=AnalysisMode.PRE_TRADE,
            pair=pair,
            signal_direction=direction,
            signal_strategy=strategy,
            signal_confidence=confidence,
            indicators=indicators,
            recent_bars=recent_bars,
            open_positions=open_positions,
            account_balance=account_balance,
        )
        return await self.analyze(request)

    async def market_review(
        self,
        pair: str,
        indicators: dict[str, Any],
        recent_bars: list[dict[str, float]],
    ) -> AIAnalysisResult:
        """Convenience: get a market overview for a pair."""
        request = AIAnalysisRequest(
            mode=AnalysisMode.MARKET_REVIEW,
            pair=pair,
            indicators=indicators,
            recent_bars=recent_bars,
        )
        return await self.analyze(request)

    # ── Post-trade review ─────────────────────────────

    async def review_closed_trade(self, trade_data: dict) -> dict:
        """Review a closed trade and return structured feedback.

        Parameters
        ----------
        trade_data : dict
            Must contain: pair, direction, entry_price, exit_price, profit,
            duration_minutes, strategy.  Optional: size, fee, stop_loss,
            take_profit.

        Returns
        -------
        dict with keys: score, lessons_learned, what_went_well,
        what_could_improve, reasoning, plus the full AIAnalysisResult fields.
        """
        pair = trade_data.get("pair", "N/A")
        direction = trade_data.get("direction", "N/A")
        strategy = trade_data.get("strategy", "N/A")

        # Build extra_context with trade details
        profit = trade_data.get("profit", 0.0)
        entry = trade_data.get("entry_price", 0.0)
        exit_ = trade_data.get("exit_price", 0.0)
        duration = trade_data.get("duration_minutes", 0)
        size = trade_data.get("size", 0.0)
        fee = trade_data.get("fee", 0.0)
        stop_loss = trade_data.get("stop_loss")
        take_profit = trade_data.get("take_profit")

        pct_change = ((exit_ - entry) / entry * 100) if entry else 0.0
        if direction.upper() == "SELL":
            pct_change = -pct_change

        extra_lines = [
            f"- Prix d'entree : {entry:.2f}",
            f"- Prix de sortie : {exit_:.2f}",
            f"- Variation : {pct_change:+.2f}%",
            f"- Taille : {size}",
            f"- Profit/Perte : {profit:+.2f} USD",
            f"- Frais : {fee:.2f} USD",
            f"- Duree : {duration} minutes",
        ]
        if stop_loss is not None:
            extra_lines.append(f"- Stop-loss : {stop_loss:.2f}")
        if take_profit is not None:
            extra_lines.append(f"- Take-profit : {take_profit:.2f}")
        extra_lines.append(f"- Resultat : {'GAGNANT' if profit >= 0 else 'PERDANT'}")

        extra_context = "\n".join(extra_lines)

        request = AIAnalysisRequest(
            mode=AnalysisMode.POST_TRADE,
            pair=pair,
            signal_direction=direction,
            signal_strategy=strategy,
            extra_context=extra_context,
        )

        result = await self.analyze(request)

        # Extract post-trade specific fields from raw response
        score = 5
        lessons_learned: list[str] = []
        what_went_well: list[str] = []
        what_could_improve: list[str] = []

        if result.raw_response:
            try:
                raw = result.raw_response.strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                parsed = json.loads(raw)
                score = int(parsed.get("score", 5))
                score = max(1, min(10, score))
                lessons_learned = parsed.get("lessons_learned", [])
                what_went_well = parsed.get("what_went_well", [])
                what_could_improve = parsed.get("what_could_improve", [])
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        return {
            "score": score,
            "lessons_learned": lessons_learned,
            "what_went_well": what_went_well,
            "what_could_improve": what_could_improve,
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "risk_warnings": result.risk_warnings,
            "market_summary": result.market_summary,
            "suggested_adjustments": result.suggested_adjustments,
            "model_used": result.model_used,
            "latency_ms": result.latency_ms,
        }

    # ── Claude API call ────────────────────────────────

    async def _call_claude(self, user_prompt: str) -> str:
        client = await self._get_client()

        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        response = await client.post(
            ANTHROPIC_API_URL,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()
        # Extract text from Claude response
        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")

        return text

    # ── Prompt building ────────────────────────────────

    def _build_prompt(self, request: AIAnalysisRequest) -> str:
        template = _PROMPT_MAP.get(request.mode, PRE_TRADE_PROMPT)

        indicators_str = self._format_dict(request.indicators)
        bars_str = self._format_bars(request.recent_bars)
        positions_str = (
            self._format_positions(request.open_positions)
            if request.open_positions
            else "Aucune position ouverte"
        )

        return template.format(
            pair=request.pair,
            direction=request.signal_direction or "N/A",
            strategy=request.signal_strategy or "N/A",
            confidence=request.signal_confidence,
            indicators=indicators_str,
            recent_bars=bars_str,
            positions=positions_str,
            balance=request.account_balance,
            extra_context=request.extra_context,
        )

    # ── Response parsing ───────────────────────────────

    def _parse_response(self, raw: str, latency_ms: int) -> AIAnalysisResult:
        """Parse Claude's JSON response into an AIAnalysisResult."""
        try:
            # Find JSON in the response (Claude may wrap it in markdown)
            json_str = raw.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            data = json.loads(json_str)

            verdict_str = data.get("verdict", "APPROVE").upper()
            try:
                verdict = AIVerdict(verdict_str)
            except ValueError:
                verdict = AIVerdict.APPROVE

            return AIAnalysisResult(
                verdict=verdict,
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                suggested_adjustments=data.get("suggested_adjustments", {}),
                market_summary=data.get("market_summary", ""),
                risk_warnings=data.get("risk_warnings", []),
                model_used=self._model,
                latency_ms=latency_ms,
                raw_response=raw,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("ai_parse_error", error=str(exc), raw=raw[:200])
            return AIAnalysisResult(
                verdict=AIVerdict.APPROVE,
                confidence=0.0,
                reasoning=f"Could not parse AI response: {raw[:300]}",
                model_used=self._model,
                latency_ms=latency_ms,
                raw_response=raw,
            )

    # ── Mode check ─────────────────────────────────────

    def _is_mode_enabled(self, mode: AnalysisMode) -> bool:
        mode_flags = {
            AnalysisMode.PRE_TRADE: settings.ai_pre_trade_enabled,
            AnalysisMode.MARKET_REVIEW: settings.ai_market_review_enabled,
            AnalysisMode.SENTIMENT: settings.ai_sentiment_enabled,
            AnalysisMode.POST_TRADE: settings.ai_post_trade_enabled,
        }
        return mode_flags.get(mode, False)

    # ── Formatting helpers ─────────────────────────────

    @staticmethod
    def _format_dict(d: dict[str, Any]) -> str:
        if not d:
            return "Aucun indicateur disponible"
        lines = []
        for k, v in d.items():
            if isinstance(v, float):
                lines.append(f"- {k}: {v:.4f}")
            else:
                lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    @staticmethod
    def _format_bars(bars: list[dict[str, float]]) -> str:
        if not bars:
            return "Aucune donnee de prix disponible"
        lines = []
        for b in bars[-10:]:  # last 10 bars only
            lines.append(
                f"O:{b.get('open', 0):.2f} H:{b.get('high', 0):.2f} "
                f"L:{b.get('low', 0):.2f} C:{b.get('close', 0):.2f} "
                f"V:{b.get('volume', 0):.0f}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_positions(positions: list[dict[str, Any]]) -> str:
        if not positions:
            return "Aucune position ouverte"
        lines = []
        for p in positions:
            lines.append(
                f"- {p.get('pair', '?')} {p.get('direction', '?')} "
                f"size={p.get('size', 0)} entry={p.get('entry_price', 0):.2f}"
            )
        return "\n".join(lines)

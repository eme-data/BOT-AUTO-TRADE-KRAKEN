"""Prompt templates for Claude AI analysis."""

from __future__ import annotations

SYSTEM_PROMPT = """Tu es un analyste crypto-trading professionnel integre dans un bot de trading automatique sur Kraken.

Ton role est d'analyser les signaux de trading generes par les strategies techniques et de fournir un avis eclaire.

Regles strictes :
- Reponds TOUJOURS en JSON valide selon le format demande
- Sois concis et factuel dans ton raisonnement
- Ne recommande jamais d'investir plus que le risk management ne le permet
- Signale clairement les risques et incertitudes
- Base tes analyses sur les donnees fournies, pas sur des suppositions
- Utilise le francais pour le raisonnement"""


POLYMARKET_CONTEXT_TEMPLATE = """## Polymarket – Marches predictifs
Sentiment global crypto : {macro_score:.0%} ({risk_level})
Facteurs cles : {key_factors}

Marches pertinents pour {pair} :
{market_list}
"""

PRE_TRADE_PROMPT = """Analyse ce signal de trading et donne ton verdict.

## Signal
- Paire : {pair}
- Direction : {direction}
- Strategie : {strategy}
- Confiance technique : {confidence:.1%}

## Indicateurs actuels
{indicators}

## Dernieres bougies (H1)
{recent_bars}

## Positions ouvertes
{positions}

## Solde du compte
{balance:.2f} USD

{polymarket_context}
{extra_context}

## Format de reponse attendu (JSON strict)
{{
  "verdict": "APPROVE" | "REJECT" | "ADJUST",
  "confidence": 0.0-1.0,
  "reasoning": "Explication en 2-3 phrases max",
  "risk_warnings": ["warning1", "warning2"],
  "suggested_adjustments": {{
    "stop_loss_pct": null ou float,
    "take_profit_pct": null ou float,
    "size_factor": null ou float (0.1-1.0)
  }},
  "market_summary": "Resume du contexte marche en 1 phrase"
}}"""


MARKET_REVIEW_PROMPT = """Fais une analyse de marche pour la paire {pair}.

## Indicateurs actuels
{indicators}

## Dernieres bougies (H1)
{recent_bars}

{extra_context}

## Format de reponse attendu (JSON strict)
{{
  "verdict": "APPROVE" | "REJECT" | "INSUFFICIENT",
  "confidence": 0.0-1.0,
  "reasoning": "Analyse du contexte de marche en 3-5 phrases",
  "risk_warnings": ["warning1"],
  "market_summary": "Resume en 1 phrase",
  "suggested_adjustments": {{}}
}}"""


SENTIMENT_PROMPT = """Analyse le sentiment de marche pour {pair} en te basant sur les donnees techniques fournies.

## Indicateurs
{indicators}

## Prix recents
{recent_bars}

{extra_context}

## Format de reponse attendu (JSON strict)
{{
  "verdict": "APPROVE" | "REJECT" | "INSUFFICIENT",
  "confidence": 0.0-1.0,
  "reasoning": "Analyse du sentiment en 2-3 phrases",
  "risk_warnings": [],
  "market_summary": "Sentiment global en 1 phrase",
  "suggested_adjustments": {{}}
}}"""


POST_TRADE_PROMPT = """Analyse ce trade cloture et fournis un retour d'experience detaille.

## Trade
- Paire : {pair}
- Direction : {direction}
- Strategie : {strategy}

## Details du trade
{extra_context}

## Format de reponse attendu (JSON strict)
{{
  "verdict": "APPROVE",
  "confidence": 1.0,
  "reasoning": "Analyse du trade : ce qui a marche, ce qui aurait pu etre mieux, en 3-4 phrases",
  "risk_warnings": [],
  "market_summary": "",
  "suggested_adjustments": {{}},
  "score": 5,
  "lessons_learned": ["Lecon 1", "Lecon 2"],
  "what_went_well": ["Point positif 1"],
  "what_could_improve": ["Amelioration 1"]
}}

Notes pour le scoring :
- score : note de 1 a 10 (1 = tres mauvais trade, 10 = trade parfait)
- Evalue la qualite de l'entree, de la sortie, le respect du risk management
- Sois objectif : un trade perdant peut avoir un bon score si l'execution etait correcte
- Un trade gagnant peut avoir un mauvais score si c'etait de la chance"""

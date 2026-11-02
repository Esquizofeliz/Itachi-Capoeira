"""Monta o prompt de sistema a partir de config/persona.txt."""
from __future__ import annotations

from .config import Config


def _tier(value: int, low: str, mid: str, high: str) -> str:
    if value < 34:
        return low
    if value < 67:
        return mid
    return high


def system_prompt(cfg: Config, memory: list[dict] | None = None) -> str:
    parts = [
        f"Você é {cfg.NAME}, um assistente de IA pessoal que roda localmente no computador do usuário.",
        "Responda sempre em português brasileiro, de forma natural, como numa conversa falada.",
        "Sua resposta será lida em voz alta: não use markdown, asteriscos, listas com marcadores, tabelas, "
        "emojis nem blocos de código. Escreva frases corridas e fáceis de ouvir.",
        "Se não souber ou não tiver certeza de algo, diga isso com honestidade em vez de inventar.",
    ]
    parts.append("Humor: " + _tier(cfg.HUMOR, "sério e direto.", "leve, com um toque de bom humor ocasional.",
                                   "bem-humorado e brincalhão, sem exagerar."))
    parts.append("Tom: " + _tier(cfg.FORMALITY, "informal e próximo.", "equilibrado entre formal e informal.",
                                 "formal e educado."))
    parts.append("Energia: " + _tier(cfg.ENTHUSIASM, "calmo e contido.", "positivo e engajado.",
                                     "animado e entusiasmado."))
    parts.append("Paciência: " + _tier(cfg.PATIENCE, "vá direto ao ponto.", "explique com cuidado quando necessário.",
                                       "explique com calma e quantas vezes for preciso."))
    if cfg.SHORT_RESPONSES:
        parts.append("Seja muito breve: no máximo duas frases.")
    else:
        parts.append("Seja conciso: normalmente de três a cinco frases, a menos que peçam mais detalhes.")
    if cfg.USE_TECHNICAL_TERMS:
        parts.append("Pode usar termos técnicos quando forem úteis.")
    else:
        parts.append("Evite jargão técnico; use palavras simples.")
    if cfg.EXPLAIN_WHILE_DOING:
        parts.append("Quando fizer algo, explique brevemente o que está fazendo.")

    if memory:
        lines = []
        for item in memory[-int(cfg.MEMORY_MAX_ITEMS):]:
            lines.append(f"- ({item.get('type', 'info')}) {str(item.get('content', ''))[:300]}")
        parts.append(
            "Contexto recente da sessão (use apenas se o usuário se referir a algo anterior, "
            "como \"o que era aquilo?\"):\n" + "\n".join(lines)
        )
    return "\n".join(parts)

"""Pipelines do assistente: tela → visão → fala, voz → texto → colar, conversa por voz, perguntas de texto."""
from __future__ import annotations

import logging
import threading

from . import audio, persona, screen
from .config import Config
from .llm import Ollama, OllamaError
from .memory import Memory
from .stt import Transcriber
from .tts import Speaker

log = logging.getLogger("itachi_capoeira")

DEFAULT_SCREEN_PROMPT = (
    "Olhe esta captura de tela e diga, de forma breve e útil, o que está acontecendo. "
    "Se houver erro, aviso ou mensagem importante, destaque. Se houver texto relevante, leia o essencial."
)


class Busy(RuntimeError):
    pass


class Assistant:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.llm = Ollama.from_config(cfg, timeout=cfg.LLM_TIMEOUT)
        self.memory = Memory(max_items=cfg.MEMORY_MAX_ITEMS, enabled=cfg.MEMORY_ENABLED)
        self.interrupt_event = threading.Event()      # interrompe fala e processamento
        self.stop_record = threading.Event()          # termina a gravação atual
        self.speaker = Speaker(cfg, self.interrupt_event)
        self.stt = Transcriber(cfg)
        self._job = threading.Lock()
        self.recording = False

    # ------------------------------------------------------------------ infra
    def _begin(self) -> None:
        if not self._job.acquire(blocking=False):
            raise Busy("O assistente já está executando outra tarefa.")
        self.interrupt_event.clear()
        self.stop_record.clear()

    def _end(self) -> None:
        self._job.release()

    @property
    def busy(self) -> bool:
        return self._job.locked()

    def interrupt(self) -> None:
        log.info("⚠️  Interrompido pelo usuário")
        self.interrupt_event.set()
        self.stop_record.set()
        self.speaker.interrupt()

    def _cancelled(self) -> bool:
        return self.interrupt_event.is_set()

    def _ensure_llm(self, *models: str) -> None:
        if not self.llm.alive():
            if self.llm.cloud:
                raise OllamaError("Não consegui falar com a nuvem do Ollama. Verifique a internet e a chave "
                                  "(itachi-capoeira cloud status).")
            raise OllamaError("O Ollama não está rodando. Inicie-o (app Ollama / 'ollama serve') e tente de novo.")
        for m in dict.fromkeys(models):
            if not self.llm.has_model(m):
                if self.llm.cloud:
                    raise OllamaError(f"Modelo '{m}' não existe na nuvem. Escolha outro: itachi-capoeira cloud setup")
                raise OllamaError(f"Modelo '{m}' não encontrado. Rode: itachi-capoeira setup   (ou: ollama pull {m})")

    def _messages(self, user_text: str) -> list[dict]:
        sys_prompt = persona.system_prompt(self.cfg, self.memory.recent())
        return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_text}]

    def _say(self, text: str) -> None:
        if text and not self._cancelled():
            self.speaker.speak(text)

    # ------------------------------------------------------------------ texto
    def answer(self, text: str) -> str:
        """Responde a um texto (sem falar) — usado internamente e por 'ask'."""
        self._ensure_llm(self.cfg.CHAT_MODEL)
        reply = self.llm.chat(self.cfg.CHAT_MODEL, self._messages(text), keep_alive=self.cfg.OLLAMA_KEEP_ALIVE,
                              num_ctx=self.cfg.NUM_CTX)
        self.memory.add("pergunta", text)
        self.memory.add("resposta", reply)
        return reply

    def ask(self, text: str, speak: bool = True) -> str:
        self._begin()
        try:
            reply = self.answer(text)
            log.info("🧠 %s", reply)
            if speak:
                self._say(reply)
            return reply
        finally:
            self._end()

    def say(self, text: str) -> bool:
        self._begin()
        try:
            return self.speaker.speak(text)
        finally:
            self._end()

    # ------------------------------------------------------------------ tela
    def describe_screen(self, question: str | None = None, speak: bool = True) -> str:
        """Print da tela → modelo de visão → resposta com personalidade → voz."""
        self._begin()
        try:
            cfg = self.cfg
            vision, chat = cfg.VISION_MODEL, cfg.CHAT_MODEL
            self._ensure_llm(vision, chat)
            log.info("📸 Capturando a tela...")
            jpeg = screen.capture_jpeg(int(cfg.SCREENSHOT_MAX_PX), int(cfg.SCREEN_MONITOR))
            img = screen.to_b64(jpeg)
            ask = question.strip() if question and question.strip() else DEFAULT_SCREEN_PROMPT
            if self._cancelled():
                return ""

            if vision == chat:
                log.info("👁️  Analisando com %s...", vision)
                reply = self.llm.chat(vision, self._messages(ask), images_b64=[img],
                                      keep_alive=cfg.OLLAMA_KEEP_ALIVE, num_ctx=cfg.NUM_CTX)
                description = reply
            else:
                if cfg.LOW_VRAM_MODE:
                    log.info("🧹 Liberando VRAM (descarregando %s)...", chat)
                    self.llm.unload(chat)
                log.info("👁️  Descrevendo com %s...", vision)
                description = self.llm.chat(
                    vision,
                    [{"role": "user", "content": "Descreva esta imagem em português brasileiro, com detalhes "
                                                 "mas de forma concisa. Transcreva textos importantes. " +
                                                 ("Pergunta do usuário: " + ask if question else "")}],
                    images_b64=[img], keep_alive=cfg.OLLAMA_KEEP_ALIVE, num_ctx=cfg.NUM_CTX)
                if not description:
                    raise OllamaError("O modelo de visão não respondeu.")
                self.memory.add("tela", description)
                if self._cancelled():
                    return ""
                if cfg.LOW_VRAM_MODE:
                    self.llm.unload(vision)
                log.info("🧠 Refinando com %s...", chat)
                reply = self.llm.chat(
                    chat,
                    self._messages(f"O usuário pediu: {ask}\nEsta é a descrição da tela dele:\n{description}\n"
                                   "Responda ao usuário de forma útil e natural."),
                    keep_alive=cfg.OLLAMA_KEEP_ALIVE, num_ctx=cfg.NUM_CTX)
                reply = reply or description

            if vision == chat:
                self.memory.add("tela", description)
            self.memory.add("resposta", reply)
            log.info("🗣️  %s", reply)
            if speak:
                self._say(reply)
            return reply
        finally:
            self._end()

    # ------------------------------------------------------------------ voz
    def _listen(self) -> str:
        """Grava uma frase e devolve a transcrição ('' se ninguém falou)."""
        cfg = self.cfg
        self.recording = True
        try:
            audio.beep(880, 110)
            log.info("🎤 Ouvindo... (fale agora)")
            clip = audio.record_command(cfg.MIC_DEVICE, cfg.MAX_RECORD_SECONDS, cfg.SILENCE_SECONDS,
                                        stop_event=self.stop_record, interrupt_event=self.interrupt_event)
        finally:
            self.recording = False
        if clip is None or self._cancelled():
            return ""
        audio.beep(660, 90)
        log.info("📝 Transcrevendo (%.1fs de áudio)...", len(clip) / audio.SAMPLE_RATE)
        text = self.stt.transcribe(clip)
        if text:
            log.info("🗒️  Reconhecimento de voz: %s", text)
        else:
            log.warning("O microfone captou áudio, mas o Whisper não reconheceu palavras. "
                        "Verifique idioma, ruído e volume da gravação.")
        return text

    def _correct(self, text: str) -> str:
        """Corrige pontuação/gramática; descarta a correção se o modelo 'inventar' demais."""
        try:
            self._ensure_llm(self.cfg.CHAT_MODEL)
            fixed = self.llm.chat(
                self.cfg.CHAT_MODEL,
                [{"role": "system", "content": "Você revisa transcrições de voz em português brasileiro. "
                  "Corrija apenas pontuação, acentuação e erros gramaticais evidentes. Não acrescente, remova nem "
                  "reescreva ideias. Responda SOMENTE com o texto corrigido, sem aspas nem comentários."},
                 {"role": "user", "content": text}],
                keep_alive=self.cfg.OLLAMA_KEEP_ALIVE, num_ctx=self.cfg.NUM_CTX, timeout=60)
        except OllamaError as e:
            log.warning("Correção gramatical indisponível (%s); usando texto bruto.", e)
            return text
        if not fixed or len(fixed) > len(text) * 2 + 20 or len(fixed) < len(text) * 0.5:
            return text
        return fixed.strip().strip('"').strip()

    def dictate(self, paste: bool | None = None) -> str:
        """Voz → texto → área de transferência (e cola, se AUTO_PASTE)."""
        self._begin()
        try:
            text = self._listen()
            if not text:
                log.info("Não ouvi nada.")
                return ""
            log.info("🗒️  Transcrição: %s", text)
            if self.cfg.CORRECT_GRAMMAR and not self._cancelled():
                text = self._correct(text)
            if not screen.set_clipboard(text):
                log.warning("Não foi possível copiar para a área de transferência.")
                return text
            log.info("📋 Copiado: %s", text)
            do_paste = self.cfg.AUTO_PASTE if paste is None else paste
            if do_paste:
                screen.paste_keystroke()
            return text
        finally:
            self._end()

    def converse(self, preset_text: str | None = None) -> str:
        """Você fala → Itachi Capoeira pensa → Itachi Capoeira responde falando."""
        self._begin()
        try:
            text = preset_text or self._listen()
            if not text:
                log.info("Não ouvi nada.")
                return ""
            log.info("🗣️  Você: %s", text)
            reply = self.answer(text)
            if not reply:
                log.warning("O Ollama retornou uma resposta vazia; não há texto para reproduzir.")
                return ""
            log.info("🧠 %s: %s", self.cfg.NAME, reply)
            self._say(reply)
            return reply
        finally:
            self._end()

    def stop_listening(self) -> None:
        self.stop_record.set()

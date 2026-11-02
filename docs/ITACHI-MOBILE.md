# 📱 Itachi Capoeira — assistente de mesa (celular por USB)

> Inspirado no projeto **Jarvis Assistant** (zapprosite): <https://github.com/zapprosite/jarvis-assistant>

`mobile/Itachi.html` transforma o celular Android numa **extensão de microfone e áudio** do PC, no estilo "assistente de mesa":
o celular escuta você, o PC pensa (Whisper + Ollama) e a resposta toca no alto-falante do celular.

## Como ligar

1. **Celular:** ative *Opções do desenvolvedor ▸ Depuração USB* e conecte o cabo. Aceite o pedido de autorização.
2. **PC:** instale o [Android Platform-Tools](https://developer.android.com/tools/releases/platform-tools) (comando `adb` no PATH) e rode:
   ```bash
   ./itachi-capoeira-gui --usb          # Windows: itachi-capoeira-gui.cmd --usb
   ```
   Isso executa `adb reverse tcp:8765 tcp:8765` e abre `http://localhost:8765/mobile/` no celular.
   Manualmente: `adb reverse tcp:8765 tcp:8765` e abra essa URL no Chrome do celular.
3. No celular, toque em **INICIAR SISTEMA**.

> Por que `localhost`? O navegador só libera o microfone em conexão segura, e `http://localhost` conta como segura.
> Por isso o caminho é o cabo USB (via `adb reverse`) e não o IP do PC no Wi-Fi.

## O que acontece ao tocar em INICIAR SISTEMA

- A página entra em **tela cheia** e mantém a tela acesa.
- Ela testa a conexão com o PC (USB) e o microfone/áudio do celular, e mostra um **aviso**:
  - ✔ tudo certo → **"CONEXÃO ESTABELECIDA"**, que **some sozinho em 15 segundos**;
  - ✖ algo falhou → aviso em vermelho dizendo **o que** falhou (PC/USB ou microfone), com **TENTAR DE NOVO**.
- Se o cabo for desconectado durante o uso, aparece **"CONEXÃO USB PERDIDA"** e o app reconecta sozinho quando o cabo voltar.
- **DESCONECTAR** (botão discreto no pé da tela) desliga o microfone, encerra a conexão e **sai da tela cheia**.
- Tocar na máscara pausa/retoma a escuta.

## Fluxo de áudio

`microfone do celular → detecção de fala (no celular) → WAV 16 kHz → POST /api/mobile/voice → Whisper → Ollama → Kokoro → WAV → alto-falante do celular`

- Sem Kokoro instalado, o PC devolve só o texto e o celular fala com a própria voz pt-BR.
- Com `WAKE_WORD_ENABLED=true` (em `config/persona.txt`), o assistente só responde quando ouvir o nome (`WAKE_WORDS`).
- Enquanto o assistente processa/fala, a escuta fica suspensa (evita ele ouvir a si mesmo).
- O servidor continua escutando **só em 127.0.0.1**; o celular chega nele pelo cabo.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| "PC não encontrado pelo USB" | Rode `itachi-capoeira-gui --usb` (ou `adb reverse tcp:8765 tcp:8765`); confira `adb devices` (deve mostrar `device`). |
| "permissão negada" no microfone | Chrome ▸ ícone de cadeado/configurações do site ▸ Microfone ▸ Permitir. |
| Erro "Ollama não está rodando" / "modelo não encontrado" | Abra o Ollama e rode `itachi-capoeira setup`. |
| Whisper demora na 1ª frase | Ele baixa o modelo no primeiro uso; use **Pré-carregar** no painel. |
| Não entra em tela cheia | Alguns navegadores (ex.: iOS/Safari) não permitem; o assistente funciona do mesmo jeito. |

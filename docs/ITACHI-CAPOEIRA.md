# 🈶 Itachi Capoeira — interface gráfica

Painel web **local** para controlar o Itachi Capoeira sem terminal. Foi *acrescentado* ao projeto: nenhum arquivo existente foi modificado.

## Como abrir

```bash
./itachi-capoeira-gui            # Linux/macOS      (Windows: itachi-capoeira-gui.cmd)
./itachi-capoeira-gui --port 9000 --no-browser
```
Requer a instalação normal (`install.sh` / `install.bat`). Abre em `http://127.0.0.1:8765`. Só aceita conexões da própria máquina
(bloqueia `Host`/`Origin` externos). Também funciona com `python -m itachi_capoeira.gui`.

## O que a interface faz

| Área | Função |
|---|---|
| **Recursos** | VRAM (GPU NVIDIA/AMD/Apple), carga de CPU e temperatura da GPU em tempo real |
| **Núcleo** | Estado do Ollama e do daemon; **Baixar tudo** (modelos pendentes) e **Limpar VRAM** |
| **Controles** | **Tela** (F9), **Voz→colar** (F8), **Conversa** (F7), **Parar** (F10). Se o daemon estiver rodando usa os mesmos gatilhos dos atalhos; senão executa na própria interface |
| **Gerenciador de I.As** | Cards dos modelos reais da configuração: chat/visão (Ollama), Faster-Whisper e Kokoro. Baixar com progresso, carregar/descarregar da VRAM |
| **Visão PT-BR** | Envia uma imagem ou captura a tela e pergunta ao modelo de visão; resposta direta em português |
| **Comandos** | Cheat-sheet gerado com seus modelos e atalhos atuais, com botão copiar |
| **Chat** | Conversa por texto com a persona e a memória do Itachi Capoeira; opção **Falar** lê a resposta em voz alta. Aceita "baixar modelos" e "limpar vram" |
| **Logs** | Últimas linhas de `itachi-capoeira.log` e `itachi-gui.log`, ao vivo |
| **Disco / Memória** | Tamanho dos modelos e espaço livre; contador e botão para limpar a memória |

## O que foi acrescentado

`itachi_capoeira/gui.py` (servidor, só biblioteca padrão) · `gui/Itachi-capoeira.html` (interface) · `itachi-capoeira-gui` e `itachi-capoeira-gui.cmd` (launchers) ·
`tests/test_gui.py` · este documento. Logs próprios em `data/logs/itachi-gui.log`.

## API local (usada pela interface)

`GET /api/status · /api/logs · /api/script` — `POST /api/ask · /api/vision · /api/trigger · /api/models · /api/memory/clear`

## Celular como microfone e áudio

O mesmo servidor entrega o assistente de mesa em `/mobile/` e recebe o áudio do celular em `POST /api/mobile/voice` (`GET /api/mobile/ping` testa a conexão).
Veja [`ITACHI-MOBILE.md`](ITACHI-MOBILE.md). Ligação por cabo: `itachi-capoeira-gui --usb`.

## Observações

- A interface abre com **itachi-capoeira-gui**; o comando de controle (terminal) continua sendo **itachi-capoeira**. Ambos fazem parte do **Itachi Capoeira**.
- Sem GPU compatível o painel mostra "CPU". Temperatura só aparece com `nvidia-smi`.
- O botão **Pré-carregar** do Whisper baixa o modelo na hora; sem ele, ele baixa no primeiro uso de voz.
- Testado com Ollama simulado (`python -m unittest`); microfone, áudio e modelos reais dependem do seu computador (`itachi-capoeira doctor --deep`).

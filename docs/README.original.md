# 🤖 Jarvis Assistant

> Seu assistente de IA pessoal 24/7 com visão, voz e personalidade brasileira.

[![Stars](https://img.shields.io/github/stars/zapprosite/jarvis-assistant?style=social)](https://github.com/zapprosite/jarvis-assistant/stargazers)
[![License](https://img.shields.io/github/license/zapprosite/jarvis-assistant)](https://github.com/zapprosite/jarvis-assistant/blob/main/LICENSE)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04-E95420?style=flat-square&logo=ubuntu)](https://ubuntu.com/)
[![Ollama](https://img.shields.io/badge/Ollama-LLM-red?style=flat-square)](https://ollama.com/)
[![Kokoro](https://img.shields.io/badge/Kokoro-TTS-blue?style=flat-square)](https://github.com/remsky/kokoro)

## 🎯 O que é?

Jarvis é um assistente de IA local que roda no seu Home Lab. Ele **vê** sua tela, **ouve** sua voz, **pensa** com inteligência e **fala** em português brasileiro — tudo offline, tudo privado.

## ⚡ Quick Start

```bash
# Clone o projeto
git clone https://github.com/zapprosite/jarvis-assistant.git
cd jarvis-assistant

# Instale com 1 comando
bash install.sh

# Execute o demo
jarvis-demo
```

## 🎮 Hotkeys

| Tecla | Ação |
|:-----:|------|
| **F8** | Gravar voz → transcrever → colar |
| **Ctrl+Print** | Screenshot → Jarvis descreve e fala |
| **Print** | Screenshot normal do Ubuntu |

## ✨ Features

### 👁️ Visão Computacional
- Captura e analisa screenshots em tempo real
- Descreve interfaces, código, mensagens
- Identifica problemas na tela

### 🎤 Voz em Português
- Transcrição com Whisper (GPU NVIDIA)
- Correção gramatical com Gemma4
- Síntese vocal com Kokoro TTS (pt-BR)

### 🧠 Inteligência Local
- 100% offline — seus dados não saem da sua máquina
- Roda com Ollama + RTX 4090
- Múltiplos modelos: LLaVA (visão), Gemma4 (raciocínio)

### 🔄 Automação
- Health check automático a cada 15 min
- Limpeza de memória quando RAM > 85%
- Restart inteligente do Ollama

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    JARVIS ASSISTANT                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  Screenshot │───▶│    LLaVA    │───▶│   Kokoro    │     │
│  │  (Print)    │    │   (Vision)  │    │    (TTS)    │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│         │                                       │             │
│         │           ┌──────────────┐          │             │
│         └──────────▶│   Gemma4     │◀─────────┘             │
│                     │ (Reasoning)  │                        │
│                     └──────────────┘                        │
│                            │                                │
│                     ┌──────────────┐                        │
│                     │   Ollama     │                        │
│                     │  (GPU/CPU)  │                        │
│                     └──────────────┘                        │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   Voice      │───▶│   Whisper    │───▶│  Clipboard   │ │
│  │   (F8)      │    │   (STT)      │    │  (Ctrl+V)    │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 📦 Stack Técnica

| Componente | Tecnologia |
|------------|------------|
| **LLM** | Ollama + Gemma4 |
| **Vision** | LLaVA |
| **TTS** | Kokoro (pt-BR) |
| **STT** | Faster-Whisper |
| **GPU** | NVIDIA RTX 4090 |
| **OS** | Ubuntu 24.04 |

## 📁 Estrutura

```
jarvis-assistant/
├── README.md              # Este arquivo
├── install.sh            # Instalador 1-click
├── jarvisctl             # Controle do serviço
├── config/
│   └── persona.txt      # Personalidade do Jarvis
├── scripts/
│   ├── jarvisd.sh        # Daemon principal
│   ├── command-mode.sh   # Pipeline visão + LLM
│   ├── ambient-listener.sh
│   ├── memory-manager.sh
│   ├── proactive-monitor.sh
│   └── ollama-health.sh  # Auto-cleanup
├── services/
│   └── jarvis.service   # Systemd autostart
└── logs/                 # Logs de execução
```

## 🚀 Como Funciona

### Ctrl+Print — Jarvis Lê a Tela

1. Captura screenshot
2. LLaVA descreve o conteúdo
3. Gemma4 analisa contexto
4. Kokoro fala em pt-BR

### F8 — Comando de Voz

1. Grava áudio do microfone
2. Faster-Whisper transcreve
3. Gemma4 corrige português
4. Copia para clipboard

### Demo Mode

```bash
jarvis-demo
```

Executa pipeline completo: hardware → models → vision → reasoning → TTS

## ⚙️ Configuração

Edite `config/persona.txt`:

```bash
NAME="Jarvis"           # Nome do assistente
VOICE="pm_santa"        # Voz Kokoro (pt-BR)
HUMOR=60                # Nível de humor (0-100)
ENTHUSIASM=80            # Nível de entusiasmo
```

## 🔧 Troubleshooting

**Jarvis não inicia?**
```bash
systemctl --user status jarvis
journalctl --user -u jarvis
```

**RAM alta?**
```bash
bash scripts/ollama-health.sh
```

**Áudio não funciona?**
```bash
curl http://localhost:8012/v1/models
```

## 📜 Licença

MIT License — use livremente.

---

## 🌟 Créditos

Feito com [Ollama](https://ollama.com/), [Kokoro TTS](https://github.com/remsky/kokoro), [LLaVA](https://llava-vl.github.io/), [Gemma4](https://ai.google.dev/gemma)

---

*Jarvis — Seu Home Lab merece um assistente à altura.* 🇧🇷

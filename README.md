<img src="gui/Itachi-em-Ginga-Brasileira.png" alt="Itachi Capoeira" width="200">

# 🤖 Itachi Capoeira — Assistente Virtual

> Assistente de IA pessoal que **vê** sua tela, **ouve** sua voz, **pensa** com modelos locais e **fala** em português brasileiro — tudo rodando localmente na sua máquina, sem enviar nada para a nuvem.

Esta é uma **iniciativa brasileira de aproximação cultural entre o Brasil e o Japão**, unindo a tecnologia de inteligência artificial com elementos da cultura brasileira.

> ⚠️ **Nota de Compatibilidade:** Atualmente, este projeto foi testado e homologado **apenas no sistema operacional Linux (Ubuntu)**.

---

## 🙏 Créditos e Origem do Projeto

Este projeto **não nasceu do zero**: ele é uma versão melhorada e adaptada do projeto original **jarvis Assistant**, criado por **zapprosite**:

👉 **Projeto oficial:** <https://github.com/zapprosite/jarvis-assistant>

A ideia, a arquitetura (visão → raciocínio → voz), a persona configurável, o conceito de memória curta, o monitor proativo e o *health check* do Ollama **vêm do trabalho do desenvolvedor original**. Se você gostou, visite e deixe uma ⭐ no repositório oficial. O README original foi preservado em [`docs/README.original.md`](docs/README.original.md).

### 🧠 Melhorias Feitas com Ajuda de Inteligência Artificial

Esta versão foi **adaptada, corrigida e ampliada com a ajuda de IAs — [OpenAI](https://openai.com/), [Claude](https://www.anthropic.com/claude) (Anthropic) e [Gemini](https://gemini.google.com/) (Google)**. Elas ajudaram a reescrever os scripts, criar o instalador, corrigir bugs e escrever a documentação e os testes. Código gerado/assistido por IA pode conter erros: **rode `itachi-capoeira doctor` e `itachi-capoeira test` no seu computador** e revise o que for usar em produção.

---

## 📊 O que mudou em relação ao original

| Categoria |                             Antes (Original)                                |                             Agora (Versão Atual)                               |
|-----------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| **Plataforma & SO** | Apenas Linux/Ubuntu (`aplay`, `scrot`, `systemd`, `free`, `/srv`) | **Linux (Ubuntu)** (Testado e otimizado com scripts em Python) |
| **Portabilidade** | Caminhos fixos (`/home/esquizofelis/Downloads/...`) | Funciona em **qualquer pasta** (caminhos dinâmicos calculados em tempo de execução) |
| **Instalação** | Manual (Ollama, Docker, Kokoro configurados um a um) | **Instalação automatizada** via script único (`install.sh`) |
| **Sintetizador (TTS)** | Exigia container Docker externo (`zappro-kokoro`) | **Kokoro via ONNX local** (sem Docker) + fallback para voz do sistema |
| **Reconhecimento (STT)** | Sem suporte a Whisper | **Faster-Whisper** integrado (suporte a GPU NVIDIA/CPU com fallback automático) |
| **Atalhos Globais** | Descritos apenas em texto conceitual | **Atalhos globais reais** configuráveis + comando `itachi-capoeira trigger` (Wayland) |
| **Pipeline de Voz** | Pendente (`TODO`) e *ambient listener* inativo | **Voz → Texto → Colar**, conversa por voz contínua e palavra de ativação opcionais |
| **Modelos de IA** | Fixos (`gemma4` ~9 GB + `llava`) | **Seleção automática por VRAM** (Gemma 4 E2B / E4B / 26B) |
| **Memória** | Registrada, mas inativa nos diálogos | Memória recente **integrada ao contexto** ativo ("o que era aquilo?") |
| **Segurança & Parsers** | JSON com concatenação frágil a aspas | JSON gerado de forma segura e sem interpolação direta em comandos |
| **Qualidade de Código** | Caracteres corrompidos/chineses em prompts e scripts (`幽默=`, `清代`) | Sanitizado e reescrito |
| **CLI & Diagnóstico** | Ferramenta `itachi-capoeira-demo` citada mas inexistente | Comando `itachi-capoeira demo` implementado + `itachi-capoeira doctor` |
| **Serviços & Logs** | Caminhos engessados e falhas de diretório no `systemd` | Geração dinâmica de caminhos no instalador e criação automática de logs |
| **Testes** | Ausentes | Conjunto de **37 testes automatizados** |

---

## 🖥️ Requisitos de Hardware

O Itachi Capoeira usa o **Gemma 4** (que entende texto **e imagem**) através do Ollama. Um único modelo faz a visão e o raciocínio — isso economiza VRAM em relação ao par LLaVA + Gemma do original.

### VRAM mínima por nível

| Nível (escolhido automaticamente) | Modelo | VRAM mínima | VRAM recomendada | Espaço em disco* |
|-----------------------------------|--------|:-----------:|:----------------:|:----------------:|
| **Econômico** | `gemma4:e2b` | **4 GB** | 6 GB | ~7,2 GB |
| **Equilibrado** ⭐ | `gemma4:e4b` | **6 GB** (o instalador só o escolhe a partir de 8 GB) | 10 GB | ~9,6 GB |
| **Máxima qualidade** | `gemma4:26b` | **20 GB** | 24 GB | > 15 GB |
| **Somente CPU** | `gemma4:e2b` | Sem GPU | — | ~7,2 GB |

*\* Somente o modelo de linguagem. Some ~0,35 GB do Kokoro (voz) e ~0,5 GB do Whisper `small`.*

> **Notas Importantes de Hardware:**
> - **Resumindo: o mínimo para rodar com GPU é ~4 GB de VRAM.** Abaixo disso (ou sem GPU compatível) ele roda na **CPU**, mas fica **bem mais lento** (respostas na casa de dezenas de segundos) e pede **8 GB de RAM** ou mais.
> - **Kokoro (voz)** roda na CPU (~0,3 GB de RAM): não consome VRAM.
> - **Whisper (ouvir você)**: usa a GPU NVIDIA se houver VRAM sobrando (~1–2 GB para o `small`); senão roda na CPU sem problema.
> - Esses números são **aproximados**, baseados na documentação/comunidade do Gemma 4 e do Ollama. Se faltar VRAM o Ollama completa com RAM/CPU (mais lento); ajuste `NUM_CTX` em `config/persona.txt` para economizar ainda mais.

### Sistemas suportados

| Sistema |                                 Situação                               |
|---------|------------------------------------------------------------------------|
| **Linux (Ubuntu)** | **Oficialmente suportado e testado.** Instalador `install.sh`. **X11:** tudo funciona. **Wayland (GNOME/Ubuntu):** os atalhos globais são registrados automaticamente no desktop (`itachi-capoeira shortcuts install`). |

---

## ⚡ Instalação (1 comando)

Você precisa só de internet e ~12 GB livres. O script instala o que faltar (Python, bibliotecas, Ollama), escolhe o modelo certo para a sua placa de vídeo, baixa tudo e roda um diagnóstico no final.

### Linux (Ubuntu)
```bash
git clone <seu-repositorio> itachi-capoeira   # ou extraia o .zip
cd itachi-capoeira
bash install.sh

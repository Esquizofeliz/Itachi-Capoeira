<img src="gui/Itachi-em-Ginga-Brasileira.png" alt="Itachi Capoeira" width="200">

# 🤖 Itachi Capoeira — Assistente Virtual

> Assistente de IA pessoal que **vê** sua tela, **ouve** sua voz, **pensa** com modelos locais e **fala** em português brasileiro — tudo rodando localmente na sua máquina, sem enviar nada para a nuvem (a nuvem do Ollama é opcional e só entra se você pedir).

Esta é uma **iniciativa brasileira de aproximação cultural entre o Brasil e o Japão**, unindo a tecnologia de inteligência artificial com elementos da cultura brasileira.

> ⚠️ **Nota de Compatibilidade:** Atualmente, este projeto foi testado e homologado **apenas no sistema operacional Linux (Ubuntu)**.

**Versão do código:** 2.0.0 · **Licença:** MIT

---

## 📑 Índice

1. [Créditos e origem](#-créditos-e-origem-do-projeto)
2. [O que mudou em relação ao original](#-o-que-mudou-em-relação-ao-original)
3. [Funcionalidades](#-funcionalidades)
4. [Requisitos de hardware](#️-requisitos-de-hardware)
5. [Instalação (Ubuntu)](#-instalação-ubuntu)
6. [Como usar](#-como-usar)
7. [Interface gráfica](#️-interface-gráfica-painel-web-local)
8. [Celular por USB](#-celular-por-usb-assistente-de-mesa)
9. [Nuvem do Ollama (sem GPU)](#️-sem-gpu-nuvem-do-ollama-opcional)
10. [Atalhos globais no Wayland](#️-atalhos-globais-no-wayland-ubuntugnome)
11. [Referência da CLI](#-referência-da-cli-itachi-capoeira)
12. [Configuração](#️-configuração)
13. [Arquitetura](#️-arquitetura)
14. [Solução de problemas](#-solução-de-problemas)
15. [Testes](#-testes)
16. [Licença e agradecimentos](#-licença-e-agradecimentos)

---

## 🙏 Créditos e Origem do Projeto

Este projeto **não nasceu do zero**: ele é uma versão melhorada e adaptada do projeto original **jarvis Assistant**, criado por **zapprosite**:

👉 **Projeto oficial:** <https://github.com/zapprosite/jarvis-assistant>

A ideia, a arquitetura (visão → raciocínio → voz), a persona configurável, o conceito de memória curta, o monitor proativo e o *health check* do Ollama **vêm do trabalho do desenvolvedor original**. Se você gostou, visite e deixe uma ⭐ no repositório oficial. O README original foi preservado em [`docs/README.original.md`](docs/README.original.md).

### 🧠 Melhorias Feitas com Ajuda de Inteligência Artificial

Esta versão foi **adaptada, corrigida e ampliada com a ajuda de IAs — [OpenAI](https://openai.com/), [Claude](https://www.anthropic.com/claude) (Anthropic) e [Gemini](https://gemini.google.com/) (Google)**. Elas ajudaram a reescrever os scripts, criar o instalador, corrigir bugs e escrever a documentação e os testes. Código gerado/assistido por IA pode conter erros: **rode `itachi-capoeira doctor` e `itachi-capoeira test` no seu computador** e revise o que for usar em produção.

### 🤝 Créditos de colaboração

Esta versão também recebeu colaboração técnica do **ChatGPT**, em conjunto com **Icaro Rodrigues Shimazu**, na análise do diagnóstico Linux, na correção do fluxo de dependências do Kokoro ONNX, do áudio/PortAudio e da captura de tela, além da documentação do procedimento de reparo. A autoria e a direção do projeto permanecem com seu criador.

---

## 📊 O que mudou em relação ao original

| Categoria | Antes (Original) | Agora (Versão Atual) |
|-----------|------------------|----------------------|
| **Plataforma & SO** | Apenas Linux/Ubuntu (`aplay`, `scrot`, `systemd`, `free`, `/srv`) | **Linux (Ubuntu)**, testado e otimizado, com a lógica em Python puro |
| **Portabilidade** | Caminhos fixos (`/home/esquizofelis/Downloads/...`) | Funciona em **qualquer pasta** (caminhos calculados em tempo de execução) |
| **Instalação** | Manual (Ollama, Docker, Kokoro configurados um a um) | **Instalação automatizada** via `install.sh` |
| **Sintetizador (TTS)** | Exigia container Docker externo (`zappro-kokoro`) | **Kokoro via ONNX local** (sem Docker) + fallback para `espeak-ng` |
| **Reconhecimento (STT)** | Sem suporte a Whisper | **Faster-Whisper** (GPU NVIDIA ou CPU, com fallback automático) |
| **Atalhos globais** | Descritos só em texto | **Atalhos reais** (F7–F10, configuráveis) + registro automático no GNOME/Wayland + `itachi-capoeira trigger` |
| **Pipeline de voz** | Pendente (`TODO`) e *ambient listener* inativo | **Voz → texto → colar**, conversa por voz e **palavra de ativação** opcional |
| **Modelos de IA** | Fixos (`gemma4` ~9 GB + `llava`) | **Seleção automática por VRAM** (Gemma 4 E2B / E4B / 26B) |
| **Memória** | Registrada, mas inativa nos diálogos | Memória recente **integrada ao contexto** ("o que era aquilo?") |
| **Interface** | Inexistente | **Painel web local** (`itachi-capoeira gráfico`) |
| **Celular** | Inexistente | **Celular Android por cabo USB** como microfone e alto-falante |
| **Nuvem** | Inexistente | **Modo nuvem opcional** (Ollama, plano gratuito, chave de API) |
| **Segurança & Parsers** | JSON com concatenação frágil a aspas | JSON gerado de forma segura; segredos em arquivo `600`; servidor só em `127.0.0.1` |
| **Qualidade de Código** | Caracteres corrompidos/chineses em prompts e scripts (`幽默=`, `清代`) | Sanitizado e reescrito |
| **CLI & Diagnóstico** | `itachi-capoeira-demo` citado, mas inexistente | `demo`, `doctor [--deep]`, `audiotest`, `health`, `config`, `test` |
| **Serviços & Logs** | Caminhos engessados e falhas de diretório no `systemd` | Caminhos dinâmicos, logs rotativos criados automaticamente, autostart (XDG ou `systemd --user`) |
| **Reparo** | Inexistente | `repair-linux.sh` para PortAudio, Kokoro e captura de tela |
| **Testes** | Ausentes | **93 funções de teste automatizadas** |

---

## ✨ Funcionalidades

| Recurso | O que faz |
|---------|-----------|
| 👁️ **Visão da tela** | Tira um print (monitor principal ou todos) e o modelo descreve, lê textos e destaca erros. Aceita uma pergunta: `itachi-capoeira screen "o que significa esse erro?"`. |
| 🎤 **Voz → texto → colar** | Grava sua fala com detecção automática de silêncio, transcreve com Faster-Whisper, **corrige pontuação/gramática** com o modelo (descarta a correção se ela "inventar" demais) e **cola** onde o cursor estiver. |
| 💬 **Conversa por voz** | Você fala, ele pensa e **responde falando**, com a personalidade configurada. |
| ⌨️ **Perguntas por texto** | `itachi-capoeira ask "..."`, com resposta falada ou só impressa. |
| 🗣️ **Fala em pt-BR** | Kokoro (ONNX, local) com vozes `pm_santa`, `pm_alex` e `pf_dora`; cai sozinho para `espeak-ng` se o Kokoro faltar ou demorar. O texto é limpo antes de falar (sem markdown, links viram "link"). |
| 👂 **Palavra de ativação** | Opcional. Mantém o microfone ouvindo e responde ao ouvir "itachi" (tolera erros do Whisper, como "itaxi"). |
| 🧠 **Memória curta** | Guarda as últimas interações em `data/memory.json` (escrita atômica) e usa o contexto quando você se refere a algo anterior. |
| 🎭 **Persona configurável** | Nome, voz, humor, formalidade, entusiasmo, paciência, respostas curtas/longas, uso de termos técnicos. |
| 🩺 **Health check do Ollama** | A cada 15 min confere o Ollama, tenta reiniciá-lo se cair e **descarrega modelos** se a RAM passar de 85% ou sobrar menos de 2 GB. |
| 👀 **Monitor proativo** | A cada 30 min avisa (notificação do desktop + voz) sobre contêineres Docker reiniciando, GPU acima de 80 °C e disco acima de 90%. |
| 🖥️ **Interface gráfica** | Painel web local com recursos, modelos, chat, visão, logs e controles. |
| 📱 **Celular por USB** | O celular Android vira microfone e alto-falante do PC, sem Wi-Fi e sem nuvem. |
| ☁️ **Nuvem opcional** | Usa modelos hospedados do Ollama (plano gratuito) quando não há GPU. |
| 🔧 **Diagnóstico e reparo** | `doctor`, `doctor --deep`, `audiotest`, `demo` e `repair-linux.sh`. |
| 🚀 **Início automático** | Opcional (XDG autostart ou `systemd --user`); **desligado por padrão**. |

---

## 🖥️ Requisitos de Hardware

O Itachi Capoeira usa o **Gemma 4** (que entende texto **e imagem**) através do Ollama. Um único modelo faz a visão e o raciocínio — isso economiza VRAM em relação ao par LLaVA + Gemma do original.

### VRAM mínima por nível

| Nível (escolhido automaticamente) | Modelo | VRAM mínima | VRAM recomendada | Espaço em disco* |
|-----------------------------------|--------|:-----------:|:----------------:|:----------------:|
| **Econômico** | `gemma4:e2b` | **4 GB** | 6 GB | ~7,2 GB |
| **Equilibrado** ⭐ | `gemma4:e4b` | **6 GB** (o instalador só o escolhe a partir de 8 GB) | 10 GB | ~9,6 GB |
| **Máxima qualidade** | `gemma4:26b` | **20 GB** (escolhido a partir de ~22 GB) | 24 GB | > 15 GB |
| **Somente CPU** | `gemma4:e2b` | Sem GPU | — | ~7,2 GB |

*\* Somente o modelo de linguagem. Some ~0,35 GB do Kokoro (voz) e ~0,5 GB do Whisper `small`.*

> **Notas Importantes de Hardware:**
> - **Resumindo: o mínimo para rodar com GPU é ~4 GB de VRAM.** Abaixo disso (ou sem GPU compatível) ele roda na **CPU**, mas fica **bem mais lento** (respostas na casa de dezenas de segundos) e pede **8 GB de RAM** ou mais.
> - **Detecção de GPU:** o instalador reconhece **NVIDIA** (`nvidia-smi`) e **AMD** (`rocm-smi`). Outras GPUs rodam como "CPU"; você pode forçar um nível com `--tier xl|m|s|cpu`.
> - **Kokoro (voz)** roda na CPU (~0,3 GB de RAM): não consome VRAM.
> - **Whisper (ouvir você)**: usa a GPU NVIDIA se houver VRAM sobrando (~1–2 GB para o `small`); senão roda na CPU sem problema. Os níveis Econômico e CPU usam o Whisper `base` na CPU.
> - Esses números são **aproximados**, baseados na documentação/comunidade do Gemma 4 e do Ollama. Se faltar VRAM o Ollama completa com RAM/CPU (mais lento); diminua `NUM_CTX` em `config/persona.txt` para economizar ainda mais.

### Sistemas suportados

| Sistema | Situação |
|---------|----------|
| **Linux (Ubuntu)** | **Oficialmente suportado e testado.** Instalador `install.sh`. **X11:** tudo funciona. **Wayland (GNOME/Ubuntu):** os atalhos globais são registrados automaticamente no desktop (`itachi-capoeira shortcuts install`). |

---

## ⚡ Instalação (Ubuntu)

Você precisa só de internet e ~12 GB livres. O script instala o que faltar (Python, pacotes do sistema, bibliotecas, Ollama), escolhe o modelo certo para a sua placa de vídeo, baixa tudo e roda um diagnóstico no final.

```bash
git clone <seu-repositorio> itachi-capoeira   # ou extraia o .zip
cd itachi-capoeira
bash install.sh
```

### O que o instalador faz (7 etapas, todas idempotentes)

1. **Python:** exige 3.10+ (recomendado **3.12**; instala `python3`, `python3-venv` e `python3-pip` pelo `apt` se faltarem).
2. **Pacotes do sistema (`apt`, pede `sudo`):** `libportaudio2`, `libsndfile1`, `xclip`, `wl-clipboard`, `espeak-ng`, `libnotify-bin`, `curl`, `zstd`.
3. **Ambiente virtual** `.venv` dentro da pasta do projeto.
4. **Bibliotecas Python** (`requirements.txt`), atalhos globais (`pynput`, sem compilar o `evdev`) e, se houver GPU NVIDIA, as bibliotecas CUDA do Whisper (~1 GB).
5. **Ollama:** instala (script oficial) e sobe o servidor, **sem abrir a janela do app**.
6. **Modelos:** escolhe o nível pela sua VRAM, baixa o Gemma 4, o Kokoro e o Whisper e grava o resultado em `config/local.txt`.
7. **Comando e atalhos:** cria o link `~/.local/bin/itachi-capoeira`, registra os atalhos do desktop (se estiver no Wayland) e **desativa** o início automático (a menos que você peça). Ao final roda o `doctor`.

### Opções do instalador

| Opção | Efeito |
|-------|--------|
| `--yes` / `-y` | Responde "sim" a tudo (sem perguntas) |
| `--tier xl\|m\|s\|cpu` | Força o nível de modelos |
| `--cloud` | Usa a nuvem do Ollama (pede a chave de API); não baixa modelos |
| `--autostart` | Liga o início automático com a sessão |
| `--skip-models` | Não baixa os modelos do Ollama |
| `--skip-tts` / `--skip-whisper` | Não baixa o Kokoro / não pré-baixa o Whisper |
| `--no-ollama` | Não instala nem inicia o Ollama |
| `--no-cuda` | Não instala as bibliotecas CUDA via pip |
| `--skip-system-deps` | Não instala pacotes do sistema |
| `--reinstall` | Recria o `.venv` do zero |

Exemplo: `bash install.sh --yes --tier s --autostart`

### Depois de instalar

```bash
itachi-capoeira demo      # testa tudo de ponta a ponta: hardware → modelos → visão → raciocínio → voz
itachi-capoeira up        # liga TUDO: atalhos globais + daemon
```

> Se o comando `itachi-capoeira` não for encontrado, use `./itachi-capoeira` dentro da pasta ou adicione `~/.local/bin` ao PATH:
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
> ```

---

## 🎮 Como Usar

### Atalhos (com o Itachi Capoeira ligado)

| Tecla | Ação |
|:-----:|------|
| **F8** | Grava voz → transcreve → **cola** onde o cursor estiver (aperte de novo para parar de gravar) |
| **F9** | Tira print da tela → o Itachi Capoeira **descreve e fala** |
| **F7** | **Conversa por voz**: você fala, ele responde falando (aperte de novo para parar de gravar) |
| **F10** | Interrompe a fala / o processamento |

Mude as teclas em `config/persona.txt` (formato pynput), por exemplo:

```ini
HOTKEY_SCREEN="<ctrl>+<print_screen>"
```

No Wayland, depois de trocar uma tecla rode `itachi-capoeira shortcuts install` de novo.

### Sem teclado: gatilhos pelo terminal

Com o daemon ligado, qualquer ação pode ser disparada por comando (útil para scripts e para o Wayland):

```bash
itachi-capoeira trigger screen    # = F9
itachi-capoeira trigger voice     # = F8
itachi-capoeira trigger talk      # = F7
itachi-capoeira trigger stop      # = F10
itachi-capoeira trigger screen --start   # liga o daemon sozinho se estiver desligado
```

### Palavra de Ativação (Opcional)

Em `config/persona.txt`:

```ini
WAKE_WORD_ENABLED=true
WAKE_WORDS="itachi,itaxi"
```

O microfone fica ouvindo e o Whisper procura o nome; ao ouvi-lo, o Itachi Capoeira responde (o que você disser logo depois do nome já vira a pergunta). Usa mais CPU e vem **desligado por padrão, por privacidade**. Enquanto ele fala ou processa, o microfone é ignorado para ele não ouvir a si mesmo. O celular também respeita essa opção.

### Personalidade e voz

Edite `config/persona.txt` (nome, voz, humor, formalidade…). Vozes pt-BR do Kokoro: `pm_santa`, `pm_alex` (masculinas) e `pf_dora` (feminina). Ajustes de hardware ficam em `config/local.txt` (gerado pelo `setup`).

### Memória

```bash
itachi-capoeira memory         # mostra o que ele lembra
itachi-capoeira clear-memory   # apaga a memória
```

---

## 🖥️ Interface gráfica (painel web local)

```bash
itachi-capoeira gráfico              # abre no navegador (aliases: grafico, gui)
itachi-capoeira gráfico --port 9000 --no-browser
./itachi-capoeira-gui                # atalho equivalente
```

Abre em `http://127.0.0.1:8765`. O servidor **só aceita conexões da própria máquina** (bloqueia `Host`/`Origin` externos). O Ollama sobe só como servidor, **sem janela**.

| Área | Função |
|------|--------|
| **Recursos** | VRAM (GPU NVIDIA/AMD), carga de CPU e temperatura da GPU em tempo real |
| **Núcleo** | Estado do Ollama e do daemon; **Baixar tudo** (modelos pendentes) e **Limpar VRAM** |
| **Controles** | **Tela** (F9), **Voz→colar** (F8), **Conversa** (F7), **Parar** (F10). Com o daemon ligado usa os mesmos gatilhos dos atalhos; senão executa na própria interface |
| **Sistema** | **LIGAR TUDO** (= `up`), **ATALHOS** (= `shortcuts install`, mostra as teclas registradas), **TESTE DE VOZ** (= `audiotest`), **NUVEM…** (= `cloud setup`, com *VOLTAR AO LOCAL* e *REINICIAR DAEMON*) |
| **Gerenciador de I.As** | Cards dos modelos reais da configuração: chat/visão (Ollama), Faster-Whisper e Kokoro. Baixar com progresso, carregar/descarregar da VRAM (no modo nuvem mostra "NUVEM") |
| **Visão PT-BR** | Envia uma imagem ou captura a tela e pergunta ao modelo de visão |
| **Comandos** | Cheat-sheet gerado com seus modelos e atalhos atuais, com botão copiar |
| **Chat** | Conversa por texto com a persona e a memória; opção **Falar** lê a resposta em voz alta |
| **Logs** | Últimas linhas de `itachi-capoeira.log` e `itachi-gui.log`, ao vivo |
| **Disco / Memória** | Tamanho dos modelos, espaço livre e botão para limpar a memória |

Mais detalhes em [`docs/ITACHI-CAPOEIRA.md`](docs/ITACHI-CAPOEIRA.md).

---

## 📱 Celular por USB (assistente de mesa)

O celular **Android** vira **microfone + alto-falante** do PC, em tela cheia, ligado por **cabo USB** (nada passa por Wi-Fi nem pela nuvem). Guia completo: [`docs/ITACHI-MOBILE.md`](docs/ITACHI-MOBILE.md).

```bash
# 1) No celular: Opções do desenvolvedor ▸ Depuração USB (aceite o aviso ao plugar o cabo)
# 2) No PC (precisa do adb / Android Platform-Tools):
sudo apt install adb
itachi-capoeira mobile        # (alias: -mobile)  ou:  ./itachi-capoeira-gui --usb
```

O comando sobe o servidor, executa `adb reverse tcp:8765 tcp:8765` e abre `http://localhost:8765/mobile/` no celular. Toque em **INICIAR SISTEMA**: a página entra em tela cheia, pede o microfone e mostra um aviso de conexão (some em 15 s; se algo falhar, diz o que faltou). Para sair, use o botão discreto **DESCONECTAR**.

**Fluxo de áudio:** `microfone do celular → detecção de fala → WAV 16 kHz → PC (Whisper → Ollama → Kokoro) → alto-falante do celular`. Sem Kokoro, o PC devolve só o texto e o celular fala com a própria voz pt-BR.

Na extensão do celular aparece também uma linha de status do PC (**IA LOCAL/NUVEM · DAEMON ATIVO/DESLIGADO**) e os botões **LIGAR TUDO NO PC** e **TESTE DE VOZ NO PC**.

---

## ☁️ Sem GPU? Nuvem do Ollama (opcional)

O Ollama tem um plano gratuito de nuvem com uso leve (os limites não são publicados e podem mudar). Crie uma chave em <https://ollama.com/settings/keys> (conta no ollama.com, sem cartão) e rode:

```bash
itachi-capoeira cloud setup      # abre a página da chave, pede a chave (não aparece na tela), lista os modelos, testa e ativa
itachi-capoeira cloud status     # modo atual, chave (mascarada) e se os modelos existem
itachi-capoeira cloud off        # volta ao Ollama local e apaga a chave
itachi-capoeira restart
```

- Na instalação: `bash install.sh --cloud` (a nuvem só entra se você pedir; nenhum modelo é baixado).
- A chave fica em `config/secrets.txt` (permissão **600**, ignorado pelo git), nunca em `persona.txt`. Também vale a variável de ambiente `OLLAMA_API_KEY`. Só é enviada por HTTPS.
- Só o raciocínio e a visão vão para a nuvem; **Whisper (voz→texto) e Kokoro (fala) continuam locais**.
- ⚠️ **Privacidade:** nesse modo o texto das conversas e **os prints da tela são enviados ao ollama.com**. Para uso 100% local, rode `cloud off`.
- Os nomes da API direta **não** levam o sufixo `:cloud` (ex.: `gpt-oss:120b`). O `cloud setup` lista o que a sua chave enxerga e escolhe um modelo de conversa e um de imagem; troque com `--chat-model` e `--vision-model`. Se "descrever a tela" falhar, o modelo escolhido provavelmente não aceita imagem.
- "Limite de uso atingido" ou "negou o acesso" = limite do plano gratuito, ou um modelo que exige plano pago.

---

## ⌨️ Atalhos globais no Wayland (Ubuntu/GNOME)

No Wayland o `pynput` só vê teclas dentro de janelas XWayland, então o Itachi Capoeira **não o usa** nessa sessão. Em vez disso, cria atalhos personalizados no GNOME que chamam `itachi-capoeira trigger <ação> --start` (o `--start` liga o daemon sozinho se ele estiver desligado).

```bash
itachi-capoeira shortcuts install   # registra F7/F8/F9/F10 (ou as teclas de HOTKEY_* em config/persona.txt)
itachi-capoeira shortcuts status    # lista o que está registrado
itachi-capoeira shortcuts remove    # apaga só os atalhos do Itachi Capoeira
```

- Roda sozinho no `install.sh`, no `setup`, no `start`, ao abrir a GUI e a cada início do daemon (desligue com `AUTO_DESKTOP_SHORTCUTS=false`).
- Funciona em **GNOME, Ubuntu, Budgie e Unity**. Seus outros atalhos não são tocados; se você trocar uma tecla em *Configurações ▸ Teclado ▸ Atalhos*, a escolha é respeitada. Conflitos com outros atalhos são avisados.
- O formato de `HOTKEY_*` é o do pynput (`<f9>`, `<ctrl>+<alt>+t`…).
- Em outros desktops (KDE, XFCE…), crie atalhos manuais que executem `/caminho/itachi-capoeira trigger screen --start` (e `voice`, `talk`, `stop`).
- Para capturar a tela no Wayland, instale `grim` (ou use uma sessão X11).

---

## 📖 Referência da CLI (`itachi-capoeira`)

### Controle do assistente

| Comando | O que faz |
|---------|-----------|
| `up` | **Liga tudo de uma vez:** registra os atalhos globais + inicia o daemon e mostra as 4 ações prontas |
| `start` / `stop` / `restart` | Inicia em segundo plano / para / reinicia |
| `run` | Roda em primeiro plano (útil para depurar) |
| `status` | Mostra ONLINE/OFFLINE (com PID) e o estado do início automático |
| `logs` | Acompanha `data/logs/itachi-capoeira.log` em tempo real |
| `trigger screen\|voice\|talk\|stop [--start]` | Aciona uma função do daemon em execução; sem ação, só configura os atalhos |
| `shortcuts install\|remove\|status` | Atalhos globais do desktop (GNOME/Wayland) |
| `autostart enable\|disable\|status [--systemd]` | Início automático com a sessão (XDG por padrão; `--systemd` usa `systemd --user`) |

### Usando o assistente

| Comando | O que faz |
|---------|-----------|
| `screen "pergunta" [--no-speak]` | Captura a tela e descreve/responde (sem pergunta, faz uma descrição geral) |
| `voice [--no-paste]` | Grava a voz → transcreve → copia (e cola) |
| `talk` | Conversa por voz |
| `ask "texto" [--no-speak]` | Pergunta por texto |
| `say "texto"` | Fala um texto |
| `memory` / `clear-memory` | Mostra / limpa a memória recente |
| `gráfico` (`grafico`, `gui`) `[--port N] [--no-browser]` | Interface gráfica no navegador |
| `mobile [--port N]` | Extensão do celular por USB |

### Diagnóstico e configuração

| Comando | O que faz |
|---------|-----------|
| `doctor [--deep]` | Diagnóstico completo (Python, venv, GPU, Ollama e modelos, Kokoro, Whisper, áudio, captura de tela, clipboard, atalhos). Com `--deep` testa de verdade o LLM, a voz e a captura |
| `demo [--no-speak]` | Demonstração em 5 etapas: hardware → modelos → visão → raciocínio → voz |
| `audiotest` | Toca uma frase e mostra em que etapa a voz falha (síntese, saída de áudio ou player) |
| `health` | Verifica Ollama, RAM, GPU e disco agora |
| `setup [--tier xl\|m\|s\|cpu] [--skip-models] [--skip-tts] [--skip-whisper]` | Reescolhe o nível pela VRAM e baixa tudo |
| `cloud setup\|status\|off [--key] [--chat-model] [--vision-model]` | Nuvem do Ollama |
| `config` | Mostra a configuração efetiva (chave de API mascarada) |
| `test` | Roda os testes automatizados |

---

## ⚙️ Configuração

A configuração é lida nesta ordem (a seguinte sobrescreve a anterior): **padrões do código → `config/persona.txt` → `config/local.txt` → `config/secrets.txt` → variáveis de ambiente `ITACHI_CAPOEIRA_<CHAVE>`**. O formato é `CHAVE="valor"`; nada é executado.

| Grupo | Chaves principais (padrão) |
|-------|----------------------------|
| **Persona** | `NAME` ("Itachi Capoeira"), `VOICE` (`pm_santa`), `LANGUAGE` (`pt-BR`), `HUMOR` (60), `FORMALITY` (40), `ENTHUSIASM` (70), `PATIENCE` (90), `SHORT_RESPONSES`, `USE_TECHNICAL_TERMS`, `EXPLAIN_WHILE_DOING` |
| **Memória** | `MEMORY_ENABLED` (true), `MEMORY_MAX_ITEMS` (10) |
| **Modelos** | `OLLAMA_URL` (`http://127.0.0.1:11434`), `CHAT_MODEL`, `VISION_MODEL` (`gemma4:e4b`), `NUM_CTX` (4096), `OLLAMA_KEEP_ALIVE` (10m), `LLM_TIMEOUT` (300), `LOW_VRAM_MODE` (false), `SCREENSHOT_MAX_PX` (1600), `SCREEN_MONITOR` (1 = principal, 0 = todos) |
| **Voz (entrada)** | `WHISPER_MODEL` (`small`), `WHISPER_DEVICE` (`auto`\|`cpu`\|`cuda`), `WHISPER_COMPUTE`, `MIC_DEVICE`, `MAX_RECORD_SECONDS` (30), `SILENCE_SECONDS` (1.4), `CORRECT_GRAMMAR` (true), `AUTO_PASTE` (true) |
| **Voz (saída)** | `TTS_ENGINE` (`auto`\|`kokoro`\|`system`\|`off`), `AUDIO_PLAYER` (`auto`\|`sounddevice`\|`system`), `AUDIO_OUT_DEVICE`, `KOKORO_SPEED` (1.0), `TTS_MAX_CHARS` (900), `TTS_SYNTH_TIMEOUT` (45 s) |
| **Atalhos** | `HOTKEY_VOICE` (`<f8>`), `HOTKEY_SCREEN` (`<f9>`), `HOTKEY_TALK` (`<f7>`), `HOTKEY_STOP` (`<f10>`), `AUTO_DESKTOP_SHORTCUTS` (true) |
| **Ativação** | `WAKE_WORD_ENABLED` (false), `WAKE_WORDS` (`itachi,itaxi`) |
| **Saúde / monitor** | `PROACTIVE_MODE` (true), `PROACTIVE_INTERVAL_MINUTES` (30), `HEALTH_INTERVAL_MINUTES` (15), `HEALTH_RAM_PERCENT` (85), `HEALTH_MIN_FREE_RAM_GB` (2), `GPU_TEMP_LIMIT` (80), `DISK_LIMIT_PERCENT` (90), `DISK_PATH`, `NOTIFY_ON_ERRORS`, `NOTIFY_ON_COMPLETIONS` |

Variáveis de ambiente de caminho: `ITACHI_CAPOEIRA_APP_DIR` (pasta do projeto) e `ITACHI_CAPOEIRA_HOME` (onde ficam `data/`, logs e modelos).

**Comportamentos que valem saber**

- Se `VISION_MODEL` e `CHAT_MODEL` forem o mesmo, a descrição de tela usa **uma única chamada** ao modelo. Se forem diferentes, ele descreve com o de visão e refina com o de conversa (`LOW_VRAM_MODE` descarrega um antes de carregar o outro).
- A resposta é escrita para ser **ouvida**: sem markdown, listas, emojis ou blocos de código.
- `TTS_ENGINE="auto"` usa o Kokoro e, se ele falhar ou passar de `TTS_SYNTH_TIMEOUT`, cai para o `espeak-ng`. O áudio toca por `sounddevice` ou pelo player do sistema (`paplay`, `aplay`, `pw-play`, `ffplay`, `play`).
- A captura de tela usa `mss` e, se falhar, `grim`, `gnome-screenshot`, `spectacle`, `scrot` ou `import`. A área de transferência usa `wl-copy`, `xclip` ou `xsel`, e a colagem envia `Ctrl+V`.

---

## 🏗️ Arquitetura

```text
 F9 / itachi-capoeira screen ─► captura (mss) ─► Gemma 4 (visão + persona + memória) ─► Kokoro TTS ─► 🔊
 F8 ─► microfone ─► VAD ─► Faster-Whisper ─► (Gemma 4 corrige) ─► clipboard ─► Ctrl+V
 F7 / "Itachi…" ─► microfone ─► Whisper ─► Gemma 4 ─► Kokoro TTS ─► 🔊
 celular (USB) ─► WAV 16 kHz ─► /api/mobile/voice ─► Whisper ─► Gemma 4 ─► Kokoro ─► alto-falante do celular
 background: health do Ollama (a cada 15 min) · monitor de disco/GPU/Docker (a cada 30 min) · gatilhos externos
```

```text
itachi-capoeira/
├── install.sh / install.py                 # instalador único
├── repair-linux.sh                         # reparo de PortAudio, Kokoro ONNX e captura de tela
├── itachi-capoeira                         # comando de controle (CLI)
├── itachi-capoeira-gui                     # abre a interface gráfica
├── config/
│   ├── persona.txt                         # personalidade e ajustes (edite à vontade)
│   ├── local.txt                           # gerado pelo setup (modelos do seu hardware)
│   └── secrets.txt                         # chave da nuvem (opcional, permissão 600)
├── itachi_capoeira/                        # código (Python)
│   ├── cli.py · daemon.py · assistant.py   # comandos, processo em segundo plano, pipelines
│   ├── llm.py · persona.py · memory.py     # Ollama, prompt de sistema, memória
│   ├── stt.py · tts.py · audio.py · wake.py# Whisper, Kokoro/espeak, gravação/VAD, ativação
│   ├── screen.py · hotkeys.py · shortcuts.py # captura/clipboard, pynput, atalhos do GNOME
│   ├── hardware.py · setup.py · doctor.py  # GPU/VRAM e níveis, download de modelos, diagnóstico
│   ├── health.py · autostart.py · cloud.py # monitor, início automático, nuvem do Ollama
│   └── gui.py · audiotest.py               # servidor do painel + ponte USB, teste de voz
├── gui/                                    # painel web local (Itachi-capoeira.html + imagens)
├── mobile/Itachi.html                      # assistente de mesa no celular (via USB)
├── tests/                                  # testes automatizados
├── docs/                                   # README.original.md, ITACHI-CAPOEIRA.md, ITACHI-MOBILE.md
├── requirements*.txt                       # dependências (base, CUDA, atalhos)
└── data/                                   # logs, memória, modelos e arquivos temporários (criado automaticamente)
```

---

## 🔧 Solução de Problemas

Comece sempre por **`itachi-capoeira doctor`** (e `itachi-capoeira doctor --deep` para testes reais). Ele diz exatamente o que falta.

- **"Ollama não responde"** → rode `ollama serve` (ou `sudo systemctl start ollama`) e depois `itachi-capoeira setup`.
- **Sem som** → rode `itachi-capoeira audiotest`; ele mostra se o problema é a síntese, a saída ou o player. Ajuste `AUDIO_PLAYER="system"` (toca no que o Ubuntu usa) ou `TTS_ENGINE="system"` (`espeak-ng`, robótica, mas imediata).
- **Sem microfone** → `sudo apt install libportaudio2`; confira o dispositivo padrão do sistema ou defina `MIC_DEVICE` (número mostrado no `doctor`).
- **Atalhos não funcionam no Wayland** → o `pynput` não captura teclas fora das janelas nessa sessão; rode `itachi-capoeira shortcuts install` e confira com `shortcuts status`.
- **Whisper na GPU falha** → ele cai sozinho para a CPU. Para forçar: `WHISPER_DEVICE="cpu"`.
- **Respostas lentas / `ollama ps` mostra CPU** → falta VRAM: use `itachi-capoeira setup --tier s` ou diminua `NUM_CTX`.
- **Logs:** `itachi-capoeira logs` (arquivo `data/logs/itachi-capoeira.log`; o daemon também escreve em `daemon-stdout.log`).

### 🔧 Reparar dependências no Linux

Se o diagnóstico apontar falhas em **Kokoro TTS**, **Áudio (PortAudio)** ou **Captura de tela**, rode na pasta do projeto:

```bash
chmod +x repair-linux.sh
./repair-linux.sh
itachi-capoeira doctor --deep
```

O script usa o `.venv` do projeto (ou o Python ativo, se não houver), instala `libportaudio2` pelo APT quando necessário (pode pedir a senha de administrador) e instala/atualiza `sounddevice`, `mss`, `kokoro-onnx` e `onnxruntime`. **Não remove** modelos, configurações, memórias nem arquivos pessoais. O diagnóstico informa a exceção real de importação do Kokoro, em vez de escondê-la.

### 🎙️ Diagnóstico de conversa por voz

Ao acionar `talk`, o Itachi identifica o microfone, grava a fala, transcreve com o Faster-Whisper, consulta o Ollama e reproduz a resposta. A linha `Saída de áudio: ...` identifica **apenas a reprodução**; ela **não confirma** que o microfone esteja captando. O log registra o dispositivo de entrada, a duração capturada e o nível RMS.

Se aparecer `Nenhuma fala detectada`, confira os dispositivos de entrada e o volume no controle de áudio do Ubuntu. Para listar dispositivos no ambiente virtual:

```bash
.venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
```

Teste a entrada direto no sistema:

```bash
arecord -l
arecord -f S16_LE -r 16000 -c 1 -d 5 /tmp/itachi-mic-test.wav
aplay /tmp/itachi-mic-test.wav
```

Se o microfone estiver correto mas a transcrição vier vazia, confirme que o idioma configurado é `pt` e que a entrada não está silenciada.

### ⚠️ Pontos críticos para o funcionamento real

1. **Servidor LLM ativo:** o Ollama precisa estar rodando na porta esperada (`http://127.0.0.1:11434`), ou a nuvem configurada.
2. **Áudio:** o `libportaudio2` precisa estar instalado no sistema.
3. **Drivers CUDA/GPU:** se você usar o Whisper na GPU NVIDIA, os drivers e as bibliotecas CUDA (`requirements-cuda.txt`) precisam ser compatíveis; senão ele usa a CPU.

---

## ✅ Testes

```bash
itachi-capoeira test      # roda toda a suíte (unittest)
```

São **93 funções de teste** em `tests/`, usando Ollama e microfone **simulados** (`tests/fake_ollama.py`). Cobrem: configuração e persona, memória, VAD e gravação, palavra de ativação e pipelines (tela, voz, conversa), síntese de voz (Kokoro e `espeak-ng`, com fallback), saída de áudio e `audiotest`, atalhos do desktop, modo nuvem, interface gráfica e API local, CLI sem tela, comando `up` e a regra de que o início automático vem desligado.

**O que foi validado no desenvolvimento** (Linux/Ubuntu, Python 3.12): instalador completo, síntese real em pt-BR com o Kokoro, captura de tela e área de transferência reais, ciclo do daemon (start/stop/status, instância duplicada, gatilhos externos, memória, logs) e todos os pipelines com Ollama e microfone simulados.

**Depende do seu computador:** GPU NVIDIA/CUDA, áudio audível (placa de som), Whisper real e os modelos Gemma reais. Por isso **`itachi-capoeira doctor --deep` é o teste definitivo**; se algo falhar, copie a saída dele ao pedir ajuda.

---

## 📜 Licença e Agradecimentos

MIT — veja [`LICENSE`](LICENSE). O projeto original informa a licença MIT; mantenha os créditos ao autor original ao redistribuir.

Construído sobre: [Ollama](https://ollama.com/) · [Gemma 4](https://ai.google.dev/gemma) (Google) · [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) e [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [mss](https://github.com/BoboTiG/python-mss) · [sounddevice](https://python-sounddevice.readthedocs.io/) · [pynput](https://github.com/moses-palmer/pynput).

---

*Itachi Capoeira — Seu computador merece um assistente à altura.* 🇧🇷

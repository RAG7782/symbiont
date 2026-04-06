# SYMBIONT — Guia de Instalacao e Configuracao

## Pre-Requisitos

- macOS 13+ ou Ubuntu 22+ (Windows via WSL2)
- 16 GB RAM minimo (32+ GB recomendado)
- 100 GB de espaco livre
- Python 3.11+
- Terminal com shell bash ou zsh

---

## Passo 1: Ollama (Motor de LLMs)

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Verificar instalacao
ollama --version

# Baixar modelos (escolha conforme sua RAM):

# === Kit Essencial (16 GB RAM) ===
ollama pull qwen3:8b           # 5.2 GB — rapido, leve
ollama pull deepseek-r1:8b     # 5.2 GB — raciocinio
ollama pull qwen3-vl:8b        # 6.1 GB — visao/OCR

# === Kit Completo (32+ GB RAM) ===
ollama pull gemma4:26b           # 17 GB — all-rounder
ollama pull qwen3.5:27b          # 17 GB — coding top-tier
ollama pull nemotron-3-nano:30b  # 24 GB — math, contexto 1M
ollama pull llama3.2-vision:11b  # 7.8 GB — visao

# Verificar modelos instalados
ollama list
```

## Passo 2: SYMBIONT (Organismo)

```bash
# Clonar o repositorio
git clone https://github.com/RAG7782/symbiont.git
cd symbiont

# Instalar com todas as dependencias
pip install -e ".[all]"

# Ou instalacao minima (sem Ollama SDK):
pip install -e .

# Ou com Ollama + IMI memory:
pip install -e ".[local]"

# Testar
sym --backend echo "Teste rapido"
sym status
```

## Passo 3: Variaveis de Ambiente

Adicione ao seu `~/.zshrc` ou `~/.bashrc`:

```bash
# Ollama otimizado
export OLLAMA_HOST=0.0.0.0
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KEEP_ALIVE=30m
export OLLAMA_NUM_PARALLEL=2
export OLLAMA_MAX_LOADED_MODELS=2

# Aliases SYMBIONT
alias sym='sym'   # ja esta no PATH apos pip install
alias sym-light='sym --light'
alias sym-cloud='sym --backend cloud'

# Aliases Ollama
alias o-code='ollama run coding'
alias o-chat='ollama run general'
alias o-reason='ollama run reasoning'
alias o-list='ollama list'
alias o-running='ollama ps'
```

## Passo 4: Presets Ollama (Opcional)

```bash
mkdir -p ~/.ollama/modelfiles

# Preset Coding
cat > ~/.ollama/modelfiles/Modelfile.coding << 'EOF'
FROM qwen3.5:27b
PARAMETER num_ctx 32768
PARAMETER temperature 0.3
SYSTEM "You are an expert software engineer."
EOF

# Preset General
cat > ~/.ollama/modelfiles/Modelfile.general << 'EOF'
FROM gemma4:26b
PARAMETER num_ctx 32768
PARAMETER temperature 0.7
SYSTEM "You are a helpful assistant."
EOF

# Preset Reasoning
cat > ~/.ollama/modelfiles/Modelfile.reasoning << 'EOF'
FROM nemotron-3-nano:30b
PARAMETER num_ctx 65536
PARAMETER temperature 0.6
SYSTEM "You are a deep reasoning assistant."
EOF

# Criar presets
ollama create coding -f ~/.ollama/modelfiles/Modelfile.coding
ollama create general -f ~/.ollama/modelfiles/Modelfile.general
ollama create reasoning -f ~/.ollama/modelfiles/Modelfile.reasoning
```

## Passo 5: IMI Memory (Opcional)

```bash
# Instalar dependencias IMI
pip install numpy chromadb sentence-transformers

# Verificar
sym memories
```

## Passo 6: Voice (Opcional)

```bash
# STT (Whisper)
pip install openai-whisper
brew install sox  # macOS

# TTS (Edge-TTS)
pip install edge-tts

# Verificar
sym voice
```

## Passo 7: GPU Cloud (Opcional)

```bash
# Modal ($30/mes gratis)
pip install modal
modal token set

# OpenRouter (precisa de API key)
export OPENROUTER_API_KEY="sua-key-aqui"

# Verificar
sym gpu
```

---

## Verificacao Final

```bash
# Tudo funcionando?
sym --backend echo "Hello SYMBIONT"   # Teste sem LLM
sym status                             # Dashboard
sym memories                           # IMI
sym gpu                                # GPU providers
sym voice                              # Voz
ollama list                            # Modelos
```

## Desinstalacao

```bash
pip uninstall symbiont
# Modelos Ollama continuam em ~/.ollama/models/
# Para remover modelos: ollama rm <modelo>
# Para remover Ollama: rm -rf ~/.ollama && brew uninstall ollama
```

---

*SYMBIONT v0.2.0*

# SYMBIONT + Ollama — Cartilha de Uso Diario

## Renato, este guia e para voce.

Voce tem 7 modelos de IA rodando no seu Mac, um organismo multi-agente com 9 agentes,
memoria persistente, visao, voz, e acesso a GPU cloud. Tudo de graca no dia a dia.

Este documento explica QUANDO usar QUAL ferramenta.

---

## 1. Decisao Rapida: Qual Comando Usar?

```
Preciso de algo?
  |
  |-- Rapido e simples? ................... sym -l "pergunta"
  |-- Codigo / implementar? .............. sym "implemente X"
  |-- Analisar imagem? ................... sym -i foto.png "o que e isso?"
  |-- Falar por voz? ..................... sym listen
  |-- Modelo 70B+ (complexo)? ............ sym-cloud "analise profunda"
  |-- GPU pesada (embeddings/finetune)? .. sym-modal "tarefa GPU"
  |-- Dentro do Claude Code? ............. ! sym "tarefa"
  |-- Chat interativo no terminal? ....... o-chat  (ou o-code, o-reason)
  |-- Roteamento automatico por tema? .... ai "minha pergunta"
  |-- Assistente de voz continuo? ........ jarvis
```

---

## 2. Mapa dos Modelos — Quando Usar Cada Um

### Modelos Locais (gratis, instantaneos)

| Modelo | Alias | Quando usar | RAM |
|--------|-------|-------------|-----|
| **qwen3:8b** | `o-fast` | Perguntas rapidas, rascunhos, brainstorm | 5 GB |
| **qwen3.5:27b** | `o-code` | Programacao, code review, debug, refactor | 17 GB |
| **gemma4:26b** | `o-chat` | Conversas gerais, analise, redacao, criativo | 17 GB |
| **nemotron-3-nano:30b** | `o-reason` | Matematica, raciocinio longo, analise juridica complexa | 24 GB |
| **deepseek-r1:8b** | `o-deep` | Chain-of-thought explicito, passo a passo | 5 GB |
| **llama3.2-vision:11b** | `o-vision` | Analisar imagens, screenshots, diagramas | 8 GB |
| **qwen3-vl:8b** | -- | OCR, ler documentos digitalizados | 6 GB |

**Regra de ouro:** Nunca rode 2 modelos grandes ao mesmo tempo (>17 GB cada).
Use `o-list` para ver o que esta carregado e `o-running` para ver o que esta ativo.

### Modelos Cloud (centavos por uso)

| Comando | Quando usar |
|---------|-------------|
| `sym-cloud "tarefa"` | Precisa de modelo 72B+ que nao cabe local |
| `sym-modal "tarefa"` | Precisa de GPU real (embeddings, batch) |

---

## 3. Fluxos do Dia a Dia por Projeto

### Warp Agents (10 agentes, CI/CD, monitoramento)

```bash
# Ver status dos agentes
cd ~/Claude\ Code/warp-agents && cat DEPLOYMENT-STATUS.md

# Kestra dashboard (workflows)
open http://localhost:8080

# Nova story
/ps create story "titulo"

# Ciclo completo
/ps validate WA-005    # @po valida
/ps implement WA-005   # @dev implementa
/ps review WA-005      # @qa revisa
/ps deploy WA-005      # @devops deploya
```

### Juridico (tributario, trabalhista, civil)

```bash
# Analise tributaria rapida (usa modelo local)
sym "Analise a incidencia de ISS sobre servicos de TI no municipio de SP"

# Analise profunda com raciocinio (Nemotron 30B, math/logica)
o-reason
>>> Calcule a base de calculo do IRPJ pelo lucro presumido para empresa de TI

# Framework injection juridico completo
/tributario "caso complexo aqui"
/fi-juridico trabalhista "rescisao indireta por assedio"

# Peca juridica
/peca "Mandado de Seguranca contra ISS sobre SaaS"
```

### AGORA / Papers Academicos

```bash
# Analise AGORA completa
/agora "tema de pesquisa"

# Analise com rotacao vetorial
sym-cloud "Analise profunda que precisa de modelo grande"

# Ler paper denso
/ler "texto do paper aqui"
```

### Coding / Desenvolvimento

```bash
# Claude Code com modelos locais (gratis)
cl-local                    # Abre Claude Code com Ollama
cl-swap qwen               # Troca para Qwen 3.5 (coding)
cl-swap gemma               # Troca para Gemma 4 (geral)

# SYMBIONT para tarefas complexas (9 agentes colaborando)
sym "Implemente autenticacao JWT com refresh tokens em FastAPI"

# Code review com visao (screenshot de UI)
sym -i screenshot.png "Identifique problemas de UX nesta tela"
```

### Fine-Tuning (criar modelo customizado)

```bash
# Ver presets disponiveis
sym finetune list

# Preparar dataset de um preset
sym finetune prepare legal-br      # Gera data/legal-br-train.jsonl
sym finetune prepare coding-python # Gera data/coding-python-train.jsonl

# Validar dataset
sym finetune validate data/legal-br-train.jsonl

# Rodar fine-tune completo (Modal GPU, ~$1-5)
sym finetune run legal-br
# Pipeline: dataset → Modal (Unsloth+LoRA) → GGUF → Ollama

# Resultado: modelo 'symbiont-legal-br' aparece no Ollama
```

### HTTP Bridge (integracoes externas)

```bash
# Iniciar o bridge (serve o Mycelium via HTTP + dashboard)
sym serve                          # Porta 7777, backend ollama
sym serve --backend echo --port 8888  # Teste sem LLM

# Abrir dashboard no browser
open http://localhost:7777         # UI com agentes, canais, colonias

# Enviar webhook ao Mycelium
curl -X POST localhost:7777/webhook \
  -H "Content-Type: application/json" \
  -d '{"channel":"meu.evento","payload":{"dado":123}}'

# Executar tarefa via HTTP
curl -X POST localhost:7777/task \
  -H "Content-Type: application/json" \
  -d '{"task":"Analise este contrato"}'
```

### Colonias Remotas (multi-servidor)

```bash
sym colony list                    # Ver colonias conhecidas
sym colony status                  # Ping todas
sym colony deploy kai              # Deploy SYMBIONT em VPS
sym colony run kai "tarefa"        # Executar remoto
sym colony heartbeat               # Health check rapido
```

### Squads (agrupamento por projeto)

```bash
sym squad list                     # Ver squads
sym squad create legal "Equipe juridica"  # Criar squad
sym squad auto                     # Auto-assign agentes por caste
```

### Federation (multi-organismo)

```bash
sym federation status              # Ver peers
sym federation add kai http://100.73.123.8:7777  # Registrar peer
```

---

## 4. Rotina Diaria Recomendada

### Manha (planejamento — use modelos potentes)

```bash
# Abrir Claude Code com Anthropic (Max subscription)
cl-claude

# Ou local se quiser economizar
cl-local

# Planejar o dia
/ps status                  # Ver stories pendentes
/ps-routing                 # Ver qual modelo usar para cada tarefa
```

### Tarde (execucao — use modelos locais)

```bash
# Implementar stories
/ps implement WA-005 task

# Para tarefas de codigo rapidas
o-code
>>> Refatore esta funcao para usar async/await

# Para analises
sym "Analise os logs de erro do ci-failure-monitor da ultima semana"
```

### Noite (consolidacao — persistir conhecimento)

```bash
# Consolidar memoria do SYMBIONT
sym dream

# Ver o que foi memorizado hoje
sym memories

# Commit do trabalho
/ps deploy WA-005
```

---

## 5. Dicas de Performance

### RAM (36 GB)

- **1 modelo grande por vez.** Qwen 3.5 (17 GB) + Gemma 4 (17 GB) = 34 GB, quase no limite.
- Use `sym -l` (light mode, so qwen3:8b = 5 GB) quando nao precisa de potencia.
- `OLLAMA_KEEP_ALIVE=30m` mantem o modelo na RAM por 30 min. Se trocar frequentemente, reduza para `5m`.

### Velocidade

- Modelos MoE (Gemma 4) sao mais rapidos que dense (Qwen 3.5) porque ativam menos parametros.
- Para respostas instantaneas: `o-fast` (qwen3:8b).
- Para streaming no terminal: `ollama run gemma4:26b` (direto, sem SYMBIONT).

### Custo

- **Local = gratis.** Use `sym`, `o-code`, `o-chat`, `ai` para 95% das tarefas.
- **Cloud = centavos.** `sym-cloud` usa OpenRouter. Monitore em https://openrouter.ai/activity
- **GPU = sob demanda.** Modal cobra por segundo. Free tier = $30/mês.

---

## 6. Troubleshooting Rapido

| Problema | Solucao |
|----------|---------|
| Modelo lento | `o-running` — ve se 2 modelos estao carregados. `ollama stop <model>` |
| "Model not found" | `o-list` — verifica se esta instalado. `ollama pull <model>` |
| Mac travando | Modelo muito grande. Use `sym -l` ou `sym-cloud` |
| sym nao funciona | `source ~/.zshrc` para recarregar aliases |
| IMI sem memorias | Normal se for primeira execucao. Vai acumulando |
| Modal timeout | Aumente timeout ou use GPU maior (L4 → A100) |

---

## 7. Referencia Rapida de Comandos

```bash
# === SYMBIONT ===
sym "tarefa"              # Full (Ollama + IMI + 9 agentes)
sym -l "tarefa"           # Light (so qwen3:8b)
sym -i img.png "analise"  # Vision
sym listen                # Voz → texto → execucao
sym-cloud "tarefa"        # OpenRouter (70B+)
sym-modal "tarefa"        # Modal GPU
sym status                # Dashboard
sym memories              # IMI stats
sym dream                 # Consolidar memorias
sym gpu                   # GPU providers
sym finetune list         # Presets de fine-tune
sym finetune prepare X    # Gerar dataset
sym finetune run X        # Rodar fine-tune (Modal)
sym voice                 # Voice capabilities
sym serve                 # HTTP bridge + dashboard
sym colony list           # Colonias remotas
sym colony run kai "X"    # Executar em colonia
sym squad list            # Squads por projeto
sym federation status     # Peers da federacao

# === OLLAMA DIRETO ===
o-code                    # Chat coding (Qwen 3.5)
o-chat                    # Chat geral (Gemma 4)
o-reason                  # Chat raciocinio (Nemotron)
o-deep                    # Chain-of-thought (DeepSeek R1)
o-vision                  # Imagens (Llama Vision)
o-list                    # Modelos instalados
o-running                 # Modelos ativos na RAM

# === CLAUDE CODE LOCAL ===
cl-local                  # Claude Code com Ollama
cl-claude                 # Claude Code com Anthropic
cl-swap gemma|qwen|nemo   # Trocar modelo on-the-fly

# === AI ROUTER ===
ai "pergunta"             # Auto-detecta melhor modelo
jarvis                    # Assistente de voz continuo

# === AIOX ===
/ps status                # Ver stories
/ps create story "titulo" # Nova story
/ps implement ID          # Implementar
/ps review ID             # QA
/ps deploy ID             # Deploy
```

---

*SYMBIONT v0.3.0 — Atualizado 2026-04-06*
*91/91 testes | 7 modelos | 5 backends | 9 agentes | IMI memory | Dashboard | Colonias | Federation*

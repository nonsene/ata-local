# Ata Local

Aplicativo local para Windows: captura áudio do sistema (Meet no navegador, Teams desktop e qualquer programa na saída selecionada) e, opcionalmente, microfone. Ao encerrar, enfileira a reunião, separa falantes, transcreve em português e gera uma ata Markdown.

**Versão 0.1.0 · Windows 64 bits · GPU NVIDIA · processamento local.** Código aberto sob licença MIT. Não usa APIs pagas, inferência em nuvem ou serviços de fila externos. Internet é necessária para instalar bibliotecas e baixar os modelos; depois disso, o aplicativo funciona offline.

## Baixar e instalar

1. Baixe `ata-local-0.1.0-windows.zip` na [página de releases](https://github.com/nonsene/ata-local/releases/latest) e extraia em uma pasta gravável, fora de `Program Files` e de pastas sincronizadas. O ZIP contém o código e os instaladores, **não um executável autônomo nem os pesos dos modelos**.
2. Instale **Python 3.12 de 64 bits** usando o [distribuidor oficial](https://www.python.org/downloads/windows/). O instalador do projeto detecta o Python Launcher (`py`) ou aceita o caminho pelo parâmetro `-Python`.
3. Abra o PowerShell na pasta extraída `ata-local` e execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Instalar.ps1
```

4. Aceite os termos do Community-1 e crie seu token de leitura, conforme a seção abaixo. Em seguida:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Autorizar-Community.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\Iniciar.ps1
```

O primeiro download é grande e pode demorar. Para indicar um Python específico, acrescente `-Python 'C:\caminho\python.exe'` ao comando de instalação. Cada pessoa utiliza sua própria conta Hugging Face para o download autorizado. Não compartilhe tokens.

Alternativamente, clone [nonsene/ata-local](https://github.com/nonsene/ata-local) e siga os mesmos passos. O arquivo `.zip.sha256` da release permite conferir o download com `Get-FileHash .\ata-local-0.1.0-windows.zip -Algorithm SHA256`.

## Requisitos e compatibilidade

- Windows 64 bits e Python 3.12 de 64 bits. macOS, Linux, GPUs AMD/Intel e execução somente em CPU não são suportados por esta distribuição.
- Configuração de referência validada: **RTX 5070 Ti de 16 GB, 32 GB de RAM e driver NVIDIA 616.56**. Outros equipamentos ainda não foram validados. Modelos e parâmetros fornecidos priorizam qualidade nessa faixa de memória.
- Driver NVIDIA compatível com PyTorch CUDA 12.8 e o runtime llama.cpp CUDA 13.4 incluído no instalador. Não é necessário instalar o CUDA Toolkit para esses binários.
- Reserve **60 GB livres** para instalação, modelos e caches, além de espaço para gravações. O consumo das gravações varia conforme canais e taxa dos dispositivos; as fontes originais são preservadas.
- Conta Hugging Face gratuita e aceite do Community-1 para o download inicial. Nenhuma assinatura paga é necessária.

## Abrir o aplicativo

Execute `Iniciar.ps1` no PowerShell. A página abre em **http://127.0.0.1:8765**. Mantenha o processo aberto; a aba do navegador pode ser fechada. **Encerrar aplicativo** na barra lateral ou `Ctrl+C` no terminal encerra o serviço. Uma captura interrompida poderá ser recuperada na interface.

Se a política do PowerShell bloquear scripts, use a exceção somente para esse processo, sem alterar a política global:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Iniciar.ps1
```

O instalador cria `.venv` dentro da pasta do projeto. Para mover a instalação, recrie esse ambiente no novo local; ambientes virtuais Python não são portáteis. O iniciador também aceita o ambiente de desenvolvimento em `../../work/venv`, mas esse diretório não faz parte da distribuição.

Não é necessário abrir o PowerShell como administrador. Se o aplicativo já estiver ativo, o iniciador reutiliza a instância. Se houver uma instância encerrando ou travada com a fila bloqueada, ele informa o problema sem iniciar outro worker. Não apague `data/worker.lock`: o Windows libera o bloqueio quando o processo proprietário encerra; o arquivo vazio pode permanecer normalmente.

## Autorizar falantes em uma nova instalação

1. Entre na sua conta e aceite as condições em [pyannote Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1).
2. Crie um [token Hugging Face de leitura](https://huggingface.co/settings/tokens) com acesso ao repositório autorizado.
3. Execute `Autorizar-Community.ps1`. Cole o token quando solicitado; a entrada fica oculta. O aplicativo não salva o token e não precisa dele para executar a inferência.

Esse aceite é uma exigência do distribuidor do modelo. Ele envolve cadastro e compartilhamento de informações de contato com o distribuidor; as gravações permanecem locais. Nenhuma API paga é usada.

## Modelos escolhidos

| Etapa | Modelo / executor | Configuração fornecida |
|---|---|---|
| Transcrição | Qwen3-ASR 1.7B em BF16 / PyTorch CUDA | Modelo multilíngue com português, sem quantização dos pesos da transcrição |
| Tempos das palavras | Qwen3-ForcedAligner 0.6B em BF16 | Alinhamento com suporte a português; texto e pontuação do ASR são preservados |
| Falantes | pyannote speaker-diarization-community-1 | Rótulos Pessoa 1, Pessoa 2 etc.; diarização exclusiva para associar palavras e detecção de sobreposição |
| Resumo | Qwen3.5 9B Q8_0 / llama.cpp CUDA | Cabe na GPU com contexto de 16.384 tokens; síntese por partes para reuniões longas |
| Fila e estado | SQLite WAL + worker Python | Persistência em disco, recuperação e um processo de inferência por etapa |

PyTorch CUDA 12.8 e llama.cpp CUDA 13.4 foram executados no hardware de referência. O áudio usa CPU; as etapas dos modelos usam GPU e são descarregadas entre processos para liberar VRAM.

A escolha é uma recomendação de engenharia para este hardware, não uma alegação de vencedor universal em reuniões pt-BR. O Qwen3-ASR suporta português e divulga bons resultados multilíngues; não há aqui um benchmark representativo das suas reuniões. Whisper large-v3 também é uma referência válida, mas não foi instalado como segundo transcritor. Para comparar qualidade real, seria necessário um conjunto de trechos das suas reuniões com transcrições corrigidas manualmente.

## Como gravar

1. Use no campo **Áudio do sistema** a mesma saída configurada no Meet/Teams.
2. Selecione seu microfone para incluir sua voz. A saída do sistema normalmente contém apenas as outras pessoas.
3. Informe título e, se possível, empresas cliente e fornecedora. O número de falantes pode ficar automático. O campo “Seu lado” fornece contexto, mas não identifica sozinho sua voz.
4. Clique **Iniciar gravação**, **Pausar/Retomar** conforme necessário e **Encerrar e processar** ao terminar.
5. A biblioteca mostra a etapa, percentual e contagem de trechos. Ao concluir, permite ler a ata, baixar `.md`, consultar a transcrição e ouvir o áudio.

O loopback captura **todos os sons da saída escolhida**, incluindo notificações. Não é uma captura isolada por processo. Use fones para que o microfone não capture novamente o áudio dos participantes. Trocar a saída ou desconectar a interface durante a gravação pode interromper a captura; o aplicativo preserva o áudio parcial e informa o erro.

As pausas são excluídas. Os tempos na transcrição se referem ao áudio resultante. Não há transcrição em tempo real: somente após encerrar.

## Cliente, fornecedor e fidelidade

O modelo recebe o contexto informado e as falas rotuladas. Vários falantes podem pertencer à mesma empresa. A ata contém uma tabela com lado, empresa, confiança e evidências. Sem evidência suficiente, a atribuição fica **indeterminada**; perguntas, sotaque ou tom de voz não são usados para determinar o lado.

Propostas são distinguidas de decisões. Responsáveis e prazos não mencionados ficam como não definidos. Fatos e ações precisam referenciar trechos existentes (`U00001` etc.), e referências inventadas são rejeitadas. Isso não prova que toda interpretação do modelo esteja correta: confira itens importantes no áudio. O sistema não reconhece nomes por biometria.

Reuniões longas são divididas segundo limites de contexto medidos pelo tokenizador do próprio modelo. Se uma resposta atingir o limite de saída, o resumidor tenta ampliar esse limite dentro do contexto disponível e, se necessário, divide o trecho automaticamente, sem aceitar JSON truncado. Cada parte validada fica salva com uma identificação baseada no conteúdo e nas configurações, permitindo retomar o resumo sem repetir as partes concluídas. Se as notas não puderem ser reduzidas mais, a ata reúne os registros extraídos e informa que pode haver repetições. Falhas que persistirem em um registro isolado continuam visíveis na interface; áudio e transcrição permanecem preservados.

## Progresso e recuperação

- O percentual corresponde à **etapa atual**, não a uma estimativa de tempo restante.
- A separação de falantes mostra o subpasso e contagem reportados pelo pyannote.
- Transcrição e resumo mostram partes concluídas / total. Durante carregamento e uma geração individual, o percentual pode ficar parado.
- A fila persiste em SQLite. Ao reiniciar, processamento interrompido retorna à fila e reutiliza checkpoints concluídos.
- Uma gravação interrompida fica disponível para **Recuperar áudio parcial**. Captura PCM e índices são gravados continuamente; falha abrupta de energia ainda pode perder buffers do sistema operacional.
- Cancelar processamento preserva arquivos. Não apaga reuniões automaticamente.
- No Windows, um Job Object vincula os processos de GPU ao aplicativo para encerrar os descendentes se ele fechar inesperadamente.

## Dados e execução offline

Tudo fica em `data/meetings/<id>/`:

| Arquivo | Conteúdo |
|---|---|
| `capture.json`, `system.pcm`, `microphone.pcm`, `*.jsonl` | Fontes originais e índices para recuperação |
| `audio.wav` | Áudio mono 16 kHz preparado |
| `speakers.json` | Intervalos e rótulos dos falantes |
| `asr-chunks/` | Checkpoints, texto original e alinhamento |
| `transcript.json`, `transcricao.md` | Transcrição com tempos e falantes |
| `summary-parts/`, `summary.json` | Extrações por trecho e ata estruturada |
| `ata.md` | Entrega final |
| `*.log` | Diagnóstico local |

Os arquivos são locais e **não são criptografados pelo aplicativo**. O projeto não tem integração com serviços de sincronização. Evite mover a pasta de dados para um diretório sincronizado se quiser mantê-la exclusivamente na máquina.

Execução: pesos carregados por caminhos locais, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, telemetria de pyannote/Hugging Face desativada, bloqueio de conexões Python fora do loopback, frontend sem CDN e servidor escutando apenas `127.0.0.1`. O llama.cpp recebe somente o arquivo GGUF local e não tem provedor de nuvem configurado. O bloqueio Python é uma proteção do aplicativo, não um firewall do Windows para qualquer programa externo.

O endpoint de escrita exige token da sessão e verifica a origem. Não exponha a porta 8765 à rede. A comunicação com llama.cpp ocorre em porta local temporária autenticada.

## Instalar em outra pasta ou máquina

Use os requisitos descritos acima. Em uma nova pasta, recrie o ambiente virtual e faça os downloads:

```powershell
.\Instalar.ps1 -Python 'C:\caminho\para\python.exe'
.\Autorizar-Community.ps1
.\Iniciar.ps1
```

Somente os scripts de instalação acessam a internet. Bibliotecas têm versões fixadas em `requirements-lock.txt`, modelos públicos em `models-lock.json`, e os ZIPs do llama.cpp têm hashes SHA-256 verificados. A revisão autorizada do Community-1 é registrada no primeiro download em `models/downloads.json`.

Não é necessário Docker, Redis, Celery, conta OpenAI, Ollama ou serviço externo. FastAPI, Uvicorn, SQLite, PyAudioWPatch e llama.cpp são gratuitos e de código aberto. O driver/runtime CUDA é software NVIDIA gratuito, com licença própria.

## Desenvolvimento e verificação

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ata_local --no-browser
```

Leia `VALIDACAO.md` para conhecer o alcance dos testes e `CONTRIBUTING.md` para contribuir. As escolhas e licenças estão em `THIRD_PARTY.md`.

Limitações atuais: os testes não constituem um benchmark de qualidade nem certificam todos os dispositivos. Uma reunião real de aproximadamente 70 minutos teve o resumo recuperado localmente, conforme `VALIDACAO.md`. Sobreposição de vozes pode produzir omissões ou atribuições incertas. Não há captura separada por aplicativo, cancelamento de eco, correção manual de falantes na interface nem serviço automático de inicialização com o Windows.

## Atualizar e resolver problemas

Encerre o aplicativo antes de substituir os arquivos de código. Preserve `data/`, `models/`, `runtime/` e as alterações que fez em `config.json`. Rode `Instalar.ps1` para atualizar as dependências; não copie a `.venv` de outro computador.

- **Fila aguardando modelos:** conclua as duas etapas de download, inclusive `Autorizar-Community.ps1`.
- **Falha de download:** execute novamente o instalador; os downloads Hugging Face aproveitam o cache local.
- **Erro CUDA ou memória insuficiente:** confira o driver e a configuração de referência. Outras GPUs podem exigir modelos e parâmetros diferentes; não há fallback automático para CPU.
- **Erro de áudio:** confira a saída usada no Meet/Teams, o microfone e as permissões de microfone dos aplicativos de desktop no Windows.
- **Resumo interrompido:** use a opção de tentar novamente na biblioteca; etapas e partes validadas são reaproveitadas.

Abra problemas em [Issues](https://github.com/nonsene/ata-local/issues), sem anexar gravações, transcrições ou tokens.

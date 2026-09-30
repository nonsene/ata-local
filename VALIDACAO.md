# Validação nesta máquina — 24/09/2026

## Distribuição pública 0.1.0 — 30/09/2026

- 35 testes automatizados passaram, incluindo empacotamento sem dados privados e retomada do download do runtime após instalação parcial.
- `pip check` não encontrou incompatibilidades declaradas; os três scripts PowerShell passaram na análise sintática.
- O ZIP foi extraído em uma pasta nova. Usando as dependências já instaladas, o código extraído iniciou, serviu a interface e informou corretamente a ausência dos modelos e de reuniões. Isso verifica independência dos caminhos do código, mas não substitui uma instalação completa em um segundo computador.
- O pacote usa uma lista explícita de arquivos, passa por verificação de padrões de credenciais e caminhos pessoais e tem SHA-256. Áudios sintéticos e reais, dados de reuniões, modelos, ambientes virtuais e binários CUDA não são distribuídos.
- A retomada do llama.cpp exige o registro de conclusão dos dois ZIPs, evitando considerar uma instalação completa apenas porque o executável já existe.
- A suíte foi executada localmente; não há workflow de inferência ou de testes em nuvem.

**Resultado: todos os modelos instalados; fluxo completo local executado com sucesso.**

Ambiente: Windows, RTX 5070 Ti (16 GB), aproximadamente 31 GiB de RAM utilizável, driver NVIDIA 616.56. PyTorch 2.11.0+cu128, qwen-asr 0.0.6, pyannote.audio 4.0.7, Transformers 4.57.6, llama.cpp b11160 CUDA 13.4. Versões completas em `requirements-lock.txt`.

## Verificações concluídas

| Verificação | Resultado |
|---|---|
| Testes automatizados | 30 passaram, incluindo bloqueio entre processos, limpeza após falha de inicialização e recuperação do resumo |
| Dependências Python (`pip check`) | Sem incompatibilidades declaradas |
| Sintaxe Python e JavaScript | Validada |
| CUDA/PyTorch | Tensor executado na RTX 5070 Ti |
| llama.cpp | CUDA0 identificado como RTX 5070 Ti; geração executada localmente |
| Dispositivos WASAPI | Saída e entrada Focusrite USB Audio reconhecidas |
| Captura simultânea | Sistema e microfone abertos; pausa/retomada/encerramento sem erro |
| Exclusão da pausa | Teste de 2,406 s ativos; áudio reconstruído com 2,402 s |
| Controles na interface | Iniciar, pausar, retomar, encerrar, envio à fila e cancelamento verificados |
| Transcrição pt-BR | Fala sintética de aproximadamente 22 s, com texto, pontuação e tempos conferidos |
| Fluxo completo da fila | Cerca de 38 s, duas vozes sintéticas pt-BR; preparação, diarização, transcrição e resumo concluídos |
| Cliente / fornecedor | Duas vozes atribuídas a Horizonte / Aurora pelas falas |
| Vários representantes | Teste adicional do resumidor com quatro falantes: dois do fornecedor e dois do cliente, todos corretamente agrupados |
| Recuperação | Teste de reinício da fila e gravação parcial preservada |
| Concorrência | Oito tentativas simultâneas obtêm somente uma posse da mesma tarefa |
| Processos no Windows | Job Object encerra subprocesso quando o proprietário fecha |
| Rede durante inferência | Acesso Python externo bloqueado; testes de DNS e conexão direta verificam o bloqueio |
| Segurança da interface local | Host, origem e token de escrita verificados |
| Token de download | Solicitado em entrada oculta, utilizado no download, não salvo pelo aplicativo |

O teste completo final está disponível na biblioteca como **Exemplo sintético — teste completo local** e em `exemplos/teste-sintetico/`. O áudio foi gerado pelas vozes instaladas do Windows, sem serviço de TTS online. Os rótulos de falantes desse teste vieram do Community-1, e a ata foi produzida pelo Qwen3.5 local.

## Limites desta validação

### Correção de inicialização e encerramento

Foi diagnosticada uma instância presa em `Shutting down`, sem porta aberta, que ainda mantinha `worker.lock` bloqueado. O log mostrou `ConnectionResetError` no transporte Proactor do Windows. Uma nova instância tentava ler o byte bloqueado antes de obter o lock, causando `PermissionError`, inclusive em PowerShell administrador.

A correção usa um loop Selector para o servidor HTTP, limita a espera de fechamento de conexões a cinco segundos, libera recursos em `finally`, consulta a saúde do servidor sem acessar SQLite e trata a disputa pelo lock antes de iniciar o Uvicorn. O iniciador reutiliza instâncias saudáveis e informa bloqueios persistentes sem traceback. Os logs não usam códigos ANSI no PowerShell.

Regressão real via Windows PowerShell: dois ciclos completos de iniciar/encerrar/reiniciar, segunda abertura reutilizando o processo existente e dez desconexões HTTP abruptas por ciclo. Ambos os encerramentos terminaram em menos de um segundo, com liberação do processo e do lock. Um lock mantido por outro processo sem servidor HTTP retorna código 2 e mensagem legível, sem traceback. Os testes usaram uma pasta de dados isolada.

### Alcance dos testes de modelos

O resumidor passou a calcular a capacidade de saída após aplicar o template real do modelo, ampliar a geração quando houver contexto livre e dividir automaticamente trechos que continuarem excedendo o limite. Testes verificam rejeição de JSON truncado, referências restritas ao trecho fornecido, cache por conteúdo e configuração, retomada após interrupção e preservação dos registros quando a consolidação não consegue reduzir as notas.

Recuperação local de uma reunião real de aproximadamente 70 minutos: somente o resumo foi reprocessado a partir da transcrição existente, com 378 falas e seis rótulos de falantes. A fila terminou como `completed`, sem erro, gerando um Markdown de 22.760 bytes. Todas as referências geradas correspondem a IDs existentes na transcrição. A consolidação preservou notas sem uma redução adicional e incluiu aviso de possíveis repetições. Nove arquivos originais, incluindo áudio bruto, áudio preparado, transcrição e índices de captura, mantiveram tamanho e SHA-256 idênticos aos registrados antes da recuperação. Essa verificação é estrutural e de integridade, não uma auditoria humana do conteúdo da reunião. Os arquivos dessa reunião não estão incluídos no pacote de código.

Não é um benchmark de qualidade em reuniões reais. Não foram medidos WER/DER em um conjunto humano de referência, comportamento em sessões de várias horas, sotaques variados, eco, perda de dispositivo, fala muito sobreposta ou mudanças de saída no meio da captura. O teste com quatro representantes verificou a interpretação do resumidor a partir de texto sintético; não foi um teste acústico de quatro vozes.

A captura usa WASAPI na saída, portanto serve para Meet e Teams quando eles reproduzem áudio nesse dispositivo. Não foi realizada uma chamada real dentro desses dois aplicativos. A aplicação preserva as gravações e referências para permitir conferir a qualidade no uso real.

O modelo pode errar palavras, omitir ações ou interpretar incorretamente uma associação mesmo com uma referência válida. Os campos de empresa ajudam o vocabulário do ASR e o contexto do resumo. Nenhuma atribuição é tratada como identificação biométrica.

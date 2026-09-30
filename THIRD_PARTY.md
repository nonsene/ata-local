# Fontes e atribuições

O código deste aplicativo é distribuído sob MIT, conforme `LICENSE`. Dependências e pesos mantêm suas próprias licenças. Os links abaixo são fontes primárias consultadas em 24/09/2026.

| Componente | Licença / fonte |
|---|---|
| Qwen3-ASR 1.7B | Apache-2.0 — [model card oficial](https://huggingface.co/Qwen/Qwen3-ASR-1.7B), [código e avaliação](https://github.com/QwenLM/Qwen3-ASR) |
| Qwen3-ForcedAligner 0.6B | Apache-2.0 — [model card oficial](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B) |
| Qwen3.5 9B | Apache-2.0 — [modelo original Qwen](https://huggingface.co/Qwen/Qwen3.5-9B), [quantização Q8_0 por Unsloth](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) |
| Community-1 | CC-BY-4.0, autoria pyannote — [model card, condições e referências](https://huggingface.co/pyannote/speaker-diarization-community-1). Pesos usados sem alteração pelo aplicativo. |
| pyannote.audio | MIT — [repositório oficial](https://github.com/pyannote/pyannote-audio) |
| PyAudioWPatch | MIT — [repositório e suporte a WASAPI](https://github.com/s0d3s/PyAudioWPatch) |
| FastAPI | MIT — [repositório oficial](https://github.com/fastapi/fastapi) |
| Uvicorn | BSD-3-Clause — [repositório oficial](https://github.com/encode/uvicorn) |
| SQLite | Domínio público — [licença oficial](https://sqlite.org/copyright.html) |
| llama.cpp | MIT — [repositório oficial](https://github.com/ggml-org/llama.cpp), [servidor local e JSON Schema](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) |
| PyTorch | BSD — [repositório oficial](https://github.com/pytorch/pytorch) |

As licenças empacotadas com cada dependência e arquivo de modelo prevalecem. Consulte também os metadados das dependências transitivas no ambiente Python. O runtime CUDA fornecido pela NVIDIA possui termos próprios; não é apresentado como código aberto.

O Whisper large-v3 foi consultado como alternativa: [model card original](https://huggingface.co/openai/whisper-large-v3). Não há chamada a modelos hospedados OpenAI neste projeto.

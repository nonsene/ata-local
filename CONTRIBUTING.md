# Contribuir

Use Windows e Python 3.12 de 64 bits. Para alterações de interface, fila e testes,
os modelos não precisam ser baixados:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Instalar.ps1 -SkipModels
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes usam dados sintéticos e pastas temporárias. Para validar inferência,
conclua os downloads descritos no README e use uma gravação de teste autorizada.
Documente separadamente testes automatizados e testes reais de modelos/GPU.

Abra uma issue com a versão, Windows, GPU, driver e mensagem de erro. Remova
nomes, conteúdo de reuniões, tokens e caminhos pessoais de qualquer log anexado.

Antes de um pull request, execute os testes e `python scripts/build_release.py`.
O empacotador usa uma lista de arquivos permitidos, verifica credenciais comuns
e gera um ZIP e seu SHA-256. Não inclua modelos, áudios ou a pasta `data/` no Git.

As contribuições ao código seguem a licença MIT do projeto. Não introduza APIs
de inferência online no fluxo padrão: processamento local é um requisito central.

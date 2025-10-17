# Plano de modularizacao do pipeline

## Diagnostico do arquivo atual
- `src/pipeline.py` concentra ~1300 linhas misturando constantes, utilitarios, IO, logica de indexacao, chamadas a modelos e orquestracao CLI.
- Ha repeticao de funcoes (`_extract_patch_operations`) e inicializacoes redundantes (`os.makedirs`).
- Dependencias externas (geradores, banco, prompts) estao acopladas diretamente, o que dificulta mockar e testar etapas isoladas.
- Estagios 1, 2 e 3 compartilham helpers privados sem fronteiras claras, expondo detalhes internos (ex.: JSON Patch, upload de arquivos) ao fluxo principal.
- Ausencia de tipos ou objetos de contexto leva a alto acoplamento global e dificulta extensoes (novos modelos, novos formatos de conhecimento).

## Objetivos da modularizacao
- Definir limites entre camadas (configuracao, servicos de dados, orquestracao de estagios, adaptadores de modelos).
- Falicitar testes unitarios e de integracao criando pontos de injecao (interfaces) para dependencias externas.
- Permitir evolucao incremental (novos formatos de indice, outros geradores) com impacto local.
- Reutilizar helpers de upload, sanitizacao e JSON Patch em outros fluxos sem duplicacao.
- Preparar base para documentar arquitetura e requisitos conforme diretrizes internas.

## Arquitetura proposta
```
src/pipeline/
    __init__.py
    config.py
    paths.py
    text_utils.py
    sanitizers.py
    index_service.py
    json_patch.py
    knowledge_models.py
    prompt_segments.py
    upload/
        __init__.py
        file_builder.py
        generator_client.py
    stages/
        __init__.py
        stage1_index.py
        stage2_knowledge.py
        stage3_cleanup.py
    runner.py
    cli.py
```
- `config.py`: constantes (MAX_WORDS_PER_UPLOAD, caminhos) e inicializacao unica de diretorios.
- `paths.py`: funcao de slug, calculo de caminhos (`get_index_file_path`, `get_docs_output_dir`).
- `text_utils.py`: funcoes gerais de texto (`_sanitize_patch_text`, `_strip_code_fences`, etc.).
- `sanitizers.py`: `_sanitize_file_list`, `_sanitize_knowledge_entry`, conversoes de sections->knowledges.
- `knowledge_models.py`: dataclasses/dicionarios tipados para Job, Knowledge, Index (facilitam anotacoes e mocks).
- `index_service.py`: carregar/salvar indice, dividir em partes, sincronizar patch, ligar com `knowledge_models`.
- `json_patch.py`: `_split_json_pointer`, `_coerce_list_index`, `_resolve_parent_and_key`, `_apply_json_patch`, `_ensure_valid_json_patch`; expor classe `JsonPatchApplier`.
- `prompt_segments.py`: `_build_files_prompt_segment`, `section_key`, geracao de blocos textuais.
- `upload/`: logica de consolidacao de arquivos e integracao com clientes de modelo (`_build_consolidated_text`, `_prepare_upload_specs`, `_perform_uploads`, `_call_generator_with_uploads`). Separar builder de arquivo (sincrono) e cliente (async) para testar sem IO real.
- `stages/`: cada estagio isolado em modulo proprio recebendo dependencias (servicos, geradores) via `PipelineContext`.
- `runner.py`: coordena chamadas aos estagios, lida com fluxo de jobs/knowledges.
- `cli.py`: encapsula argparse e expoe `asyncio.run` chamando runner; `src/pipeline.py` vira simples thin wrapper ou some apos migracao.

## Mapeamento de funcoes chave
| Bloco atual                                   | Responsabilidade principal                                 | Destino sugerido                                   |
|-----------------------------------------------|-------------------------------------------------------------|----------------------------------------------------|
| Constantes e `os.makedirs`                    | Configuracao compartilhada                                  | `config.py`                                        |
| `slugify`, `_sanitize_temp_identifier`        | Utilitarios de texto/caminho                                | `paths.py` e `text_utils.py`                       |
| Funcoes de sanitizacao de knowledges          | Normalizacao de entradas                                    | `sanitizers.py`                                    |
| `_convert_sections_to_knowledges`             | Conversao de formatos de indice                             | `sanitizers.py` ou `knowledge_models.py`           |
| `_extract_file_names`, `_lookup_related_names`| Interpretacao de registros do banco                         | `knowledge_models.py`                              |
| JSON Patch helpers                            | Aplicacao e validacao de patches                            | `json_patch.py`                                    |
| `_format_file_entry`..`_predict_upload_names` | Preparacao e previsao de uploads                            | `upload/file_builder.py`                           |
| `_perform_uploads`..`_call_with_retries`      | Integracao com geradores e politicas de retry               | `upload/generator_client.py`                       |
| `_write_conversation_log`                     | Persistencia de chat debug                                  | `runner.py` (ou utilitario dedicado)               |
| `process_input_folder`                        | Carga inicial de jobs                                       | `runner.py` ou `stages/stage0_input.py` futuro     |
| `run_stage1_index_creation`                   | Estagio 1 (indexacao)                                       | `stages/stage1_index.py`                           |
| `process_pending_knowledges`                  | Estagio 2 (conteudo)                                        | `stages/stage2_knowledge.py`                       |
| `run_stage3_cleanup`                          | Estagio 3 (finalizacao)                                     | `stages/stage3_cleanup.py`                         |
| `main`                                        | CLI/entrada                                                 | `cli.py`                                           |

## Plano de execucao em fases
1. **Preparacao**: criar pacote `src/pipeline/`, mover constantes para `config.py`, eliminar repeticoes de `os.makedirs`, configurar import relativo.
2. **Utilitarios de texto e caminhos**: extrair `slugify`, `_sanitize_patch_text`, `_strip_code_fences` e helpers correlatos para `text_utils.py` e `paths.py`. Ajustar chamadas.
3. **Sanitizacao e modelos**: mover funcoes de normalizacao e conversao para `sanitizers.py` e introduzir dataclasses (ou TypedDicts) em `knowledge_models.py`. Atualizar `index_service`.
4. **Servico de indice**: criar `index_service.py` englobando `get_index_part_paths`, `_write_index_files`, `load_index_data`, `save_index_data`, `_convert_sections_to_knowledges`. Introduzir classe `IndexService` com metodos coesos.
5. **JSON Patch**: migrar helpers para `json_patch.py`, remover duplicacao de `_extract_patch_operations`, expor funcao/classe unica. Cobrir com testes focados.
6. **Upload/generator**: separar construcao de arquivos (`file_builder.py`) de chamadas async (`generator_client.py`). Permite mockar client e reusar retry policy.
7. **Prompts e segmentos**: extrair `_build_files_prompt_segment`, `section_key`, e logica de listagem para `prompt_segments.py`.
8. **Estagios**: criar modulos em `stages/` recebendo dependencias via `PipelineContext` (ex.: database service, generators, index_service, upload_service). Cada modulo expor funcao `run(context)`.
9. **Runner e CLI**: implementar `runner.py` que instancia contexto, orquestra estagios e substitui logica de `main`. `cli.py` encapsula argparse e chama runner via `asyncio.run`.
10. **Higienizacao final**: remover funcoes obsoletas do arquivo antigo, atualizar imports em outros modulos, garantir que `docs/architecture.md` e `docs/requirements.md` sejam revisados.

## Consideracoes adicionais
- Introduzir `PipelineContext` centralizando dependencias (paths, services, geradores) para facilitar testes e troca de implementacoes.
- Planejar criacao de testes unitarios para `json_patch`, `index_service` e `upload` antes ou durante migracao para evitar regressao.
- Garantir que a configuracao de logs e escrita de arquivos temporarios permaneça em um unico ponto (`config.py` ou `runner.py`).
- Revisar manipulacao de event loop ao mover funcoes async para evitar chamadas aninhadas de `asyncio.run`, conforme orientacoes do projeto sobre paralelismo.
- Atualizar documentacao de arquitetura e requisitos ao final de cada fase relevante, mantendo fontes de verdade sincronizadas.
- Avaliar criacao de scripts de migrao incremental para nao bloquear pipeline atual (feature flag ou CLI antigo durante transicao).

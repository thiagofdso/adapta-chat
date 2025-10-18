# Plano de processamento em lotes

## Objetivo
- Registrar e controlar todo o fluxo de merge hierarquico de conhecimentos por meio de lotes persistidos no banco SQLite (`data/pipeline.db`).
- Garantir rastreabilidade de quais arquivos compoem cada lote, em que estagio estao, qual foi o resultado produzido e como reprocessar em caso de falha.
- Alinhar a documentacao ao comportamento atual de `src/pipeline.py`, preparando o terreno para evolucoes modulares descritas em `plano-pipeline.md`.

## Estado atual do pipeline
- **Entrada (estagio 0)**: `process_input_folder` escaneia uma pasta de arquivos `.txt`, cria um registro em `jobs` por arquivo (`status_id = 1`) e guarda metadados de caminho.
- **Estagio 1** (`run_stage1_index_creation`): para cada job pendente gera/atualiza `indexes/<slug>.json` e popula a tabela `knowledges` com entradas extraidas; arquivos associados sao registrados em `files_knowledges`.
- **Estagio 2** (`process_pending_knowledges`): gera markdowns em `docs_<slug>/*.md` usando os registros pendentes na tabela `knowledges` e marca `status_id = 3` ao concluir.
- **Estagio 3** (`run_stage3_cleanup`): encerra os jobs que possuem todos os conhecimentos com `status_id = 3`.
- **Banco atual**: tabelas `jobs`, `knowledges`, `files_knowledges`, `knowledge_relations`. Nao ha hoje rastreamento de lotes nem de agregacoes entre jobs.

## Estrutura de diretorios esperada
- `data/pipeline.db` - banco SQLite central do pipeline.
- `indexes/` - indice completo e partes (`*_part_###.json`) gerados no estagio 1.
- `docs_<slug>/` - markdowns finais por conhecimento (estagio 2).
- `01_staging/` - raiz de staging para lotes.
  - `01_staging/lotes/` - configuracoes de agrupamento por lote (`lote_config.json`) e pastas `lote_##`.
    - `01_staging/lotes/lote_##/input/` - copias ou symlinks para os JSONs individuais vindos dos jobs.
    - `01_staging/lotes/lote_##/output/` - resultados consolidados da fase corrente.
  - `01_staging/fase_01_resultados/` - JSONs consolidados apos a fase 1.
  - `01_staging/fase_02_resultados/` - JSONs consolidados apos a fase 2.
- `02_processed/` - armazena `indice_final.json` e artefatos finais.
- `logs/` - registros operacionais escritos por `utils/logger.py`.
- `01_staging/prompt_lote.txt` - arquivo unico contendo o prompt utilizado no processamento mais recente; deve ser sobrescrito a cada lote.

## Modelo de dados proposto para lotes

### Tabelas existentes (referencia)
| Tabela | Campos chave | Uso |
|--------|--------------|-----|
| `jobs` | `id`, `file_path`, `folder_path`, `stage_id`, `status_id` | Rastrea arquivos brutos e em que estagio/estado eles estao (`1=pendente`, `2=processando`, `3=concluido`). |
| `knowledges` | `id`, `job_id`, `knowledge_id_from_json`, `name`, `status_id` | Guarda conhecimentos extraidos por job; `status_id` segue mesma codificacao numerica. |
| `files_knowledges` | `id`, `knowledge_id`, `file_name` | Lista os arquivos fonte vinculados a cada conhecimento. |
| `knowledge_relations` | `id`, `knowledge_id`, `related_knowledge_id` | Reserva de relacionamentos manual/automatico entre conhecimentos (ainda nao utilizada). |

### Novas tabelas
| Tabela | Campos principais | Descricao |
|--------|------------------|-----------|
| `batch_runs` | `id`, `stage` (`phase1`, `phase2`, `final`), `parent_batch_id`, `status_id`, `input_count`, `output_count`, `token_estimate`, `max_batch_size`, `created_at`, `started_at`, `finished_at`, `error_message` | Controla cada execucao de lote. `status_id` segue `1=pendente`, `2=processando`, `3=concluido`, `4=falhou`, `5=descartado`. `parent_batch_id` conecta lotes de fases posteriores aos de origem. |
| `batch_items` | `id`, `batch_id`, `job_id`, `knowledge_id`, `input_path`, `output_path`, `input_order`, `status_id`, `notes` | Materializa a composicao de cada lote. No inicio (`stage='phase1'`) apenas `job_id` sera preenchido, apontando para o JSON individual gerado pelo job. Em fases seguintes, `knowledge_id` registra os conhecimentos consolidados utilizados como entrada. |
| `batch_files` | `id`, `batch_id`, `file_path`, `file_size_bytes` | Mantem rastreamento de arquivos fisicos gerados (ex.: `lote_01_consolidado.json`, `indice_final.json`). |
| `batch_metrics` (opcional) | `id`, `batch_id`, `metric_key`, `metric_value` | Flexivel para armazenar contagens especificas (tempo de execucao, numero de deduplicacoes, etc.) sem alterar schema. |

### Views/indices recomendados
- `CREATE INDEX idx_batch_runs_stage_status ON batch_runs(stage, status_id);`
- `CREATE INDEX idx_batch_items_batch_id ON batch_items(batch_id);`
- `CREATE INDEX idx_batch_items_knowledge_id ON batch_items(knowledge_id);`
- `CREATE INDEX idx_batch_files_batch_id ON batch_files(batch_id);`

## Ciclo de vida de um lote
1. **Planejamento**: identificar JSONs individuais prontos para processamento (jobs com arquivos vigentes). Registrar `batch_runs` com `status_id = 1` e preencher `batch_items` com os `job_id` e caminhos dos arquivos em `01_staging/lotes/lote_##/input/`.
2. **Preparacao**: calcular `token_estimate`, `input_count` e `max_batch_size` (default 10). Atualizar `status_id = 2` em `batch_runs` quando iniciar o processamento.
3. **Processamento fase 1**: agrupar ate `max_batch_size` entradas, enviar ao LLM usando o prompt de deduplicacao (ver secao de prompts). Salvar output JSON em `01_staging/lotes/lote_##/output/` e copiar para `01_staging/fase_01_resultados/`. Atualizar `batch_items.output_path` e registrar o artefato em `batch_files`.
4. **Processamento fase 2**: ler os JSON consolidados da fase 1, formar novos lotes menores (ex.: tamanho 5) e repetir o processo, preenchendo `knowledge_id` em `batch_items` conforme conhecimentos resultantes forem inseridos na tabela `knowledges`. Ligar `batch_runs.parent_batch_id` e registrar os novos arquivos em `01_staging/fase_02_resultados/`.
5. **Finalizacao**: consolidar resultado final em `02_processed/indice_final.json` e (quando necessario) gerar markdowns adicionais. Marcar `batch_runs.status_id = 3` quando todos os `batch_items` estiverem concluidos.
6. **Falhas**: capturar excecoes e mover o lote para `status_id = 4`, guardando `error_message` e timestamps. Permitir acao de retry criando novo `batch_runs` relacionado ao anterior (campo `retry_of_batch_id` se necessario).

## Fluxo operacional por fase
### Preparar entradas
- Rodar `poetry run python src/pipeline.py --input <pasta>` para popular `jobs` e gerar knowledges.
- Usar consulta SQL para localizar conhecimentos prontos: `SELECT id FROM knowledges WHERE status_id = 3`.

### Fase 1 (lotes iniciais)
- Criar lotes de ate 10 conhecimentos, preferindo agrupar por `folder_path` ou tema quando possivel.
- Persistir o agrupamento em `batch_runs` (`stage = 'phase1'`) e `batch_items`.
- Enviar os JSONs para o LLM usando o prompt definido em `src/prompts/knowledge_deduplication_phase1.txt` (a ser criado). Registrar `output_path`.
- Atualizar `output_count` com o numero de conhecimentos no JSON consolidado (do campo `knowledges`).

### Fase 2 (merge hierarquico)
- Coletar os JSONs consolidados (`batch_runs.stage = 'phase1'` `status_id = 3`), dividir em lotes de tamanho 5.
- Repetir a chamada ao LLM (prompt da fase 2), gerando agregados maiores. Atualizar `parent_batch_id` com referencia ao lote de origem.
- Se o resultado ainda possuir mais de um JSON, repetir novas fases criando novos registros em `batch_runs` ate restar um unico lote final.

### Persistencia final
- Escrever `indice_final.json` em `02_processed/`.
- Opcional: gerar markdowns adicionais ou alimentar `docs_<slug>/` reutilizando `process_pending_knowledges` se novos conhecimentos forem criados.
- Atualizar `batch_files` com checksum (MD5/SHA256) para rastreabilidade.

## Fallback e reprocessamento
- Utilizar a funcao `dividir_lote_por_tokens` como fallback automatico, registrando em `batch_metrics` o numero de subdivisoes.
- Em caso de `status_id = 4`, manter os `batch_items` congelados para auditoria. Um retry deve clonar os registros para novo `batch_runs` com referencia ao anterior (`retry_of_batch_id` opcional).
- Registrar sempre `error_message`, `started_at`, `finished_at` para diagnostico.
- Armazenar o prompt utilizado em `01_staging/prompt_lote.txt`, sobrescrevendo a cada execucao conforme orientado.

## Monitoramento e auditoria
- Reutilizar `utils.logger.logger` para logs estruturados; incluir `batch_id` e `item_id` em cada mensagem.
- Criar consulta padrao: `SELECT * FROM batch_runs WHERE status_id IN (1,2)` para queue interno.
- Disponibilizar dashboard simples (por exemplo, comando `poetry run python scripts/report_batches.py`) que imprima contagens por status e tempo medio por fase.

## Estrategia de merge hierarquico para deduplicacao de conhecimentos

### Fase 1: agrupamento em lotes (Batch Clustering)
Divida os JSONs individuais (arquivos produzidos pelos jobs) em lotes de ate 10 arquivos cada. Use o prompt a seguir:

```
Analise estes JSONs de conhecimentos e identifique duplicatas semanticamente.
Para conhecimentos similares, consolide em uma unica entrada mantendo:
- Nome mais representativo
- Descricao que capture todos os aspectos
- Lista de todos os arquivos fonte

Retorne JSON consolidado no formato:

{
    "knowledges": [
        {
            "name": "Nome do conhecimento",
            "description": "Descricao consolidada",
            "files":  ["arquivo1.txt", "arquivo2.txt"]
        }
    ]
}
```

### Fase 2: merge hierarquico dos lotes
Pegue os JSONs consolidados da fase 1 e agrupe-os em lotes de ate 5 arquivos. Repita o prompt reforcando:

- Identificar conhecimentos com sobreposicao semantica (nao apenas identicos).
- Mesclar descricoes complementares.
- Unificar listas de arquivos fonte.
- Preservar nuances importantes que diferenciam conhecimentos similares.

Repita ate obter um unico JSON consolidado.

## Estrategia de fallback

Caso um lote exceda limites de tokens ou caracteres, aplique divisao automatica:

```python
def dividir_lote_por_tokens(jsons, max_chars=50000):
    lotes = []
    lote_atual = []
    chars_atuais = 0

    for json_obj in jsons:
        tamanho = len(json.dumps(json_obj))
        if chars_atuais + tamanho > max_chars:
            lotes.append(lote_atual)
            lote_atual = [json_obj]
            chars_atuais = tamanho
        else:
            lote_atual.append(json_obj)
            chars_atuais += tamanho

    if lote_atual:
        lotes.append(lote_atual)
    return lotes
```

Documente a divisao no campo `batch_metrics` com a chave `split_count`.

## Prompt para deduplicacao semantica

Use o seguinte prompt base quando precisar deduplicar conhecimentos:

```
Voce e um especialista em organizacao de conhecimento. Analise os conhecimentos extraidos das transcricoes anexadas.

TAREFA:
1. Identifique conhecimentos que tratam do MESMO conceito/tecnica/ideia (nao apenas texto identico)
2. Para cada grupo de conhecimentos similares:
   - Crie UMA entrada consolidada
   - Use o nome mais claro e descritivo
   - Combine as descricoes preservando todas as nuances importantes
   - Liste TODOS os arquivos fonte

CRITERIOS DE SIMILARIDADE:
- Mesmo conceito tecnico com nomenclaturas diferentes
- Descricoes complementares do mesmo assunto
- Exemplos diferentes da mesma tecnica

IMPORTANTE:
- Mantenha conhecimentos DISTINTOS separados mesmo que relacionados
- Nao perca informacao relevante na consolidacao
- Quando em duvida, mantenha separado

Retorne JSON no formato especificado.
```

## Consideracoes de execucao
- Manter o processamento central com `asyncio` como no pipeline atual; se paralelizar tarefas de IO pesado (ex.: leitura de arquivos grandes), usar `concurrent.futures.ThreadPoolExecutor` via `loop.run_in_executor`.
- Evitar manipulacao manual de event loop em funcoes que rodarao dentro do Streamlit; expor operacoes de lote como chamadas sincronicamente aguardadas.
- O tamanho do lote deve ser configuravel via `MAX_BATCH_SIZE_PHASE1` e `MAX_BATCH_SIZE_PHASE2` no modulo de configuracao.
- Salvar qualquer artefato gerado em pastas versionadas por data (`02_processed/2025-10-18/`) para facilitar auditoria, registrando o caminho em `batch_files`.

## Roadmap de implementacao
1. **Migracao de banco**: criar script incremental (`poetry run python scripts/migrate_batches.py`) que adicione as novas tabelas e indices sem afetar dados existentes.
2. **Servicos de acesso**: implementar funcoes em `src/database.py` (`create_batch`, `append_batch_item`, `update_batch_status`, `list_pending_batches`) mantendo coesao com o estilo atual.
3. **Adaptacao do pipeline**: adicionar novo estagio (ex.: `run_stage4_batch_merge`) que consome as tabelas de lote e executa as fases 1/2/3 conforme descrito.
4. **Persistencia de artefatos**: padronizar funcoes utilitarias para salvar outputs de lote e registrar automaticamente em `batch_files`.
5. **Relatorios e monitoramento**: criar script/CLI para inspecionar batches e integrar com logs existentes.
6. **Documentacao**: atualizar `docs/architecture.md` e `docs/requirements.md` com o fluxo de lote e diagramas; manter este arquivo como referencia operacional.

## Decisoes confirmadas
- Os lotes sao montados a partir dos JSONs individuais gerados pelos jobs; conhecimentos consolidados entram apenas nas fases seguintes.
- Manter a estrutura `01_staging/...` para inputs e outputs de cada fase, reutilizando `fase_01_resultados` e `fase_02_resultados`.
- Nao ha necessidade de armazenar checksums nos registros de arquivos.
- Guardar o prompt mais recente em `01_staging/prompt_lote.txt`, sobrescrevendo-o a cada processamento.
- Nao existe SLA formal para duracao de lotes; monitoramento pode focar em contagens e status.

# Compatibilidade com AdaptaClient

## Escopo
Relatorio solicitando quais funcoes expostas em `src/generators/adapta/client.py` sao exigidas indiretamente por `src/pipeline.py` e `src/app_chat.py` via os geradores Adapta. A analise considera os geradores instanciados em cada fluxo e os metodos do cliente acessados por eles.

## Funcoes exigidas por `src/pipeline.py`
| Funcao no AdaptaClient | Como o pipeline aciona | Referencias |
| --- | --- | --- |
| `_ensure_client` (`src/generators/adapta/client.py:172`) | Toda chamada a `generator.call_model_with_messages` comeca invocando `generator._ensure_client_initialized`, que por sua vez executa `await self.client._ensure_client()`; esse encadeamento acontece quando `_call_with_retries` dispara `generator.call_model_with_messages` para Claude Opus, GPT ou Gemini (`src/pipeline.py:790`, `src/generators/adapta/claude_opus_generator.py:33-36`, `src/generators/adapta/gpt_generator.py:33-36`, `src/generators/adapta/gemini_generator.py:33-36`). | `src/pipeline.py:790`, `src/generators/adapta/claude_opus_generator.py:33`, `src/generators/adapta/gpt_generator.py:33`, `src/generators/adapta/gemini_generator.py:33` |
| `call_model` (`src/generators/adapta/client.py:640`) | `_call_generator_with_existing_uploads` delega para `generator.call_model_with_messages(..., file_ids=[...], tool=tool)` (`src/pipeline.py:790`). Cada implementacao de gerador apenas repassa para `self.client.call_model` preservando parametros como `searchType`, `tool`, `chat_id` e anexos (`src/generators/adapta/claude_opus_generator.py:92`, `src/generators/adapta/gpt_generator.py:94`, `src/generators/adapta/gemini_generator.py:94`). | `src/pipeline.py:790`, `src/generators/adapta/claude_opus_generator.py:92`, `src/generators/adapta/gpt_generator.py:94`, `src/generators/adapta/gemini_generator.py:94` |
| `upload_arquivo` (`src/generators/adapta/client.py:493`) | Durante `_perform_uploads`, o pipeline chama explicitamente `await generator.client.upload_arquivo(str(upload_path))` para cada arquivo que precisa ser anexado antes da chamada ao modelo (`src/pipeline.py:754-768`). | `src/pipeline.py:754-768`, `src/generators/adapta/client.py:493` |
| `excluir_arquivo` (`src/generators/adapta/client.py:610`) | Depois de usar um arquivo temporario, `_cleanup_upload_infos` remove os anexos remotos com `await generator.client.excluir_arquivo(file_id)` para evitar lixo na conta (`src/pipeline.py:802-810`). | `src/pipeline.py:802-810`, `src/generators/adapta/client.py:610` |

> Nao foram encontrados outros acessos a `generator.client` dentro do pipeline, portanto esses quatro metodos representam todo o contrato atual entre `pipeline.py` e `AdaptaClient`.

## Funcoes exigidas por `src/app_chat.py`
| Funcao no AdaptaClient | Como o app aciona | Referencias |
| --- | --- | --- |
| `_ensure_client` (`src/generators/adapta/client.py:172`) | O app instancia diversos geradores (Gemini, Claude, GPT, Claude Opus, Deepseek, Grok-4, GPT-OSS, Deepseek-R1, O3 e O4-Mini) em `initialize_generators` (`src/app_chat.py:11-33`). Sempre que o usuario envia uma mensagem, `selected_generator.call_model_with_messages(...)` e invocado (`src/app_chat.py:115-142`), o que novamente passa por `_ensure_client_initialized` -> `self.client._ensure_client()` em cada classe de gerador (`src/generators/adapta/claude_generator.py:33-36`, `src/generators/adapta/gpt_generator.py:33-36`, `src/generators/adapta/gemini_generator.py:33-36`, etc.). | `src/app_chat.py:115-142`, `src/generators/adapta/claude_generator.py:33`, `src/generators/adapta/gpt_generator.py:33`, `src/generators/adapta/gemini_generator.py:33` |
| `call_model` (`src/generators/adapta/client.py:640`) | A mesma chamada `selected_generator.call_model_with_messages` repassa mensagens do chat, parametros de busca (`searchType`) e ferramentas (`tool`) diretamente para `AdaptaClient.call_model`, preservando o `chat_id` gerado no Streamlit (`src/app_chat.py:121-141`, `src/generators/adapta/claude_generator.py:92`, `src/generators/adapta/gpt_generator.py:94`, `src/generators/adapta/gemini_generator.py:94`, e equivalentes nos demais geradores). | `src/app_chat.py:121-141`, `src/generators/adapta/claude_generator.py:92`, `src/generators/adapta/gpt_generator.py:94`, `src/generators/adapta/gemini_generator.py:94` |

> O aplicativo de chat nao realiza uploads diretos nem limpezas de arquivos; por isso `upload_arquivo` e `excluir_arquivo` nao sao exercitados nesse fluxo.

## Conclusoes
- Tanto o pipeline quanto o app dependem fortemente de `AdaptaClient.call_model`, portanto qualquer mudanca de assinatura ou de comportamento (ex.: suporte a `searchType`, `tool`, `chat_id` ou anexos) deve ser sincronizada com **todas** as implementacoes de geradores.
- O pipeline adiciona duas dependencias adicionais (`upload_arquivo`, `excluir_arquivo`) porque precisa gerenciar anexos manualmente antes e depois de chamar o modelo.
- `AdaptaClient._ensure_client` e parte critica da inicializacao em ambos os contextos; se ele passar a ser privado de fato ou renomeado, sera necessario ajustar cada gerador que o invoca.

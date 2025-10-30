# Backlog – Paridade entre `AdaptaClient` e `AdaptaClientV2`

1. **Implementar `call_model` compatível com o cliente legado**  
   - Aceitar listas de mensagens (não apenas `prompt` simples).  
   - Suportar os parâmetros opcionais `searchType`, `tool`, `chat_id` e `file_ids` tal como no `AdaptaClient`.  
   - Normalizar a resposta em texto único (com opção `new_line`) para não quebrar os chamadores atuais.

2. **Normalizar anexos de arquivos em chamadas de chat**  
   - Recriar o fluxo `_prepare_files_payload`, `_resolve_files_payload` e `_resolve_messages_payload` usando os novos endpoints.  
  - Permitir apontar arquivos por ID e preencher metadados automaticamente antes de enviar mensagens ao modelo.

3. **Expor helpers de formatos de arquivo**  
   - Adicionar `is_formato_aceito()` e `get_formatos_aceitos()` para manter a API utilitária esperada pelo código existente.  
   - Garantir que `upload_file` valide formatos reutilizando esses helpers.

4. **Compatibilidade com APIs legadas de arquivos**  
   - Criar um alias `obter_arquivos()` que delega para `list_files()` e devolve a mesma estrutura esperada pelo código legado.  
   - Disponibilizar wrappers `upload_arquivo()` e `excluir_arquivo()` que usem os novos endpoints mas preservem assinatura/retorno antigos (inclusive suporte a exclusão por ID).

5. **Saúde e manutenção de sessão**  
   - Implementar `health_check()` equivalente, reutilizando o fluxo atual de login/token para confirmar que o cliente está apto.  
   - Avaliar necessidade de rate limit / “touch” de sessão semelhante a `_update_session` para manter compatibilidade com cenários de longa duração.

6. **Limpeza automática de chats efêmeros**  
   - Repor o comportamento do `AdaptaClient` que apagava conversas temporárias após cada chamada quando `chat_id` não era fornecido, aproveitando `delete_chats()`.

7. **Retry com alternância de modelos**  
   - Reintroduzir a lógica de `_create_conversation_with_retry` (retries exponenciais e alternância entre modelos) para cenários onde Claude/Gemini precisam de fallback automático.

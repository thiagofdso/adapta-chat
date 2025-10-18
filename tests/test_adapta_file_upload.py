import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

# Garante que o diretório src esteja no PYTHONPATH para importações locais
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generators.adapta.client import AdaptaClient  # noqa: E402
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator  # noqa: E402


class TestUploadAndFileUsage(IsolatedAsyncioTestCase):
    """Valida o upload e o uso de arquivos em mensagens usando o modelo Claude Opus."""

    async def asyncSetUp(self) -> None:
        self.client = AdaptaClient(
            cookies_str="__session=fake_token; other=value",
            session_id="sess_fake_123",
        )
        # Evita chamadas reais à rede durante os testes
        self.client._ensure_client = AsyncMock()
        self.client._update_session = AsyncMock()

        self.direct_upload_payload = {
            "success": True,
            "data": {
                "fileKey": "user/test/arquivo_teste.txt",
                "uploadUrl": "https://s3.aws/upload",
                "requiredHeaders": {"Content-Type": "text/plain"},
                "ttlSeconds": 3600,
            },
        }

        self.metadata_payload = {
            "success": True,
            "data": {
                "id": "file_123",
                "fileName": "arquivo_teste.txt",
                "fileSizeInBytes": 28,
                "fileMimeType": "text/plain",
                "filePathOnStorage": "user/test/arquivo_teste.txt",
            },
        }

        upload_response = MagicMock()
        upload_response.json.return_value = self.direct_upload_payload
        metadata_response = MagicMock()
        metadata_response.json.return_value = self.metadata_payload

        self.client._make_request = AsyncMock(side_effect=[upload_response, metadata_response])
        self.client._create_conversation_with_retry = AsyncMock()
        self.client._delete_conversations = AsyncMock()
        self.client.obter_arquivos = AsyncMock(return_value=[self.metadata_payload["data"]])

        self.client.client = MagicMock()
        self.client.client.put = AsyncMock(
            return_value=MagicMock(status_code=200, raise_for_status=MagicMock())
        )

    async def test_upload_and_use_file_with_claude_opus(self) -> None:
        """Garante que o arquivo é enviado e utilizado em uma mensagem do modelo CLAUDE_OPUS."""
        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "arquivo_teste.txt"
            content = "Conteúdo de teste para upload."
            file_path.write_text(content, encoding="utf-8")

            uploaded_data = await self.client.upload_arquivo(str(file_path))

            self.assertEqual(uploaded_data, self.metadata_payload["data"])
            self.assertEqual(self.client._make_request.await_count, 2)

            primeira_chamada = self.client._make_request.await_args_list[0]
            self.assertIn("json", primeira_chamada.kwargs)
            inicio_payload = primeira_chamada.kwargs["json"]
            self.assertEqual(inicio_payload["originalFilename"], file_path.name)
            self.assertEqual(inicio_payload["sizeInBytes"], len(content.encode("utf-8")))
            self.assertEqual(inicio_payload["mimeType"], "text/plain")

            segunda_chamada = self.client._make_request.await_args_list[1]
            self.assertIn("json", segunda_chamada.kwargs)
            metadata_payload = segunda_chamada.kwargs["json"]
            self.assertEqual(metadata_payload["fileKey"], self.direct_upload_payload["data"]["fileKey"])
            self.assertEqual(metadata_payload["sizeInBytes"], len(content.encode("utf-8")))
            self.assertEqual(metadata_payload["mimeType"], "text/plain")

            self.assertEqual(self.client.client.put.await_count, 1)
            put_call = self.client.client.put.await_args_list[0]
            self.assertEqual(put_call.args[0], self.direct_upload_payload["data"]["uploadUrl"])
            self.assertEqual(put_call.kwargs["headers"]["Content-Type"], "text/plain")

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.text = '0:"Resposta simulada a partir do arquivo"'
        self.client._create_conversation_with_retry.return_value = fake_response

        generator = ClaudeOpusGenerator(
            cookies_str="__session=fake_token; other=value",
            session_id="sess_fake_123",
        )
        generator.client = self.client
        generator._client_initialized = False

        messages = [
            {
                "role": "user",
                "content": "Leia e resuma o arquivo enviado.",
            }
        ]

        result = await generator.call_model_with_messages(messages)
        self.assertEqual(result, "Resposta simulada a partir do arquivo")

        self.assertEqual(self.client._create_conversation_with_retry.await_count, 1)
        convo_call = self.client._create_conversation_with_retry.await_args
        self.assertEqual(convo_call.args[0], messages)
        self.assertEqual(convo_call.args[1], generator.model_name)
        self.assertEqual(convo_call.kwargs.get("files_payload"), [])

        self.client._create_conversation_with_retry.reset_mock()
        new_response = MagicMock()
        new_response.status_code = 200
        new_response.text = '0:"Resposta simulada com arquivos"'
        self.client._create_conversation_with_retry.return_value = new_response

        anexos_ids = ["file_123"]
        result_with_files = await generator.call_model_with_messages(messages, file_ids=anexos_ids)
        self.assertEqual(result_with_files, "Resposta simulada com arquivos")

        self.assertEqual(self.client._create_conversation_with_retry.await_count, 1)
        convo_call = self.client._create_conversation_with_retry.await_args
        self.assertEqual(convo_call.kwargs.get("files_payload"), [self.metadata_payload["data"]])

    async def test_prepare_files_payload_helper(self) -> None:
        vazio = AdaptaClient._prepare_files_payload(None)
        self.assertEqual(vazio, [])

        somente_ids = AdaptaClient._prepare_files_payload(["f1", 2])
        self.assertEqual(somente_ids, [{"id": "f1"}, {"id": "2"}])

        objetos = [{"id": "f3", "name": "Arquivo 3"}, {"fileId": "f4"}]
        self.assertEqual(
            AdaptaClient._prepare_files_payload(objetos),
            [{"id": "f3", "name": "Arquivo 3"}, {"fileId": "f4", "id": "f4"}],
        )


class TestRetryAlternatingModels(IsolatedAsyncioTestCase):
    """Garante que os modelos Claude e Gemini sao alternados nas retentativas."""

    async def asyncSetUp(self) -> None:
        self.client = AdaptaClient(
            cookies_str="__session=fake_token; alt=value",
            session_id="sess_fake_retry",
        )
        self.client._ensure_client = AsyncMock()
        self.client._update_session = AsyncMock()

    async def test_retry_cycle_inicia_com_gemini(self) -> None:
        mensagens = [{"role": "user", "content": "Teste de retry"}]
        resposta_final = MagicMock(status_code=200, text='0:"ok"')
        self.client._create_conversation = AsyncMock(
            side_effect=[Exception("Falha 1"), Exception("Falha 2"), resposta_final]
        )

        resultado = await self.client._create_conversation_with_retry(
            mensagens,
            "GEMINI",
            max_retries=3,
            delay=0.0,
        )

        self.assertIs(resultado, resposta_final)
        chamadas = self.client._create_conversation.await_args_list
        self.assertEqual(len(chamadas), 3)
        self.assertEqual(chamadas[0].args[1], "GEMINI")
        self.assertEqual(chamadas[1].args[1], "CLAUDE_4")
        self.assertEqual(chamadas[2].args[1], "GEMINI")

    async def test_retry_cycle_inicia_com_claude(self) -> None:
        mensagens = [{"role": "user", "content": "Teste com Claude"}]
        resposta_final = MagicMock(status_code=200, text='0:"ok"')
        self.client._create_conversation = AsyncMock(
            side_effect=[Exception("Falha inicial"), resposta_final]
        )

        resultado = await self.client._create_conversation_with_retry(
            mensagens,
            "CLAUDE_4",
            max_retries=3,
            delay=0.0,
        )

        self.assertIs(resultado, resposta_final)
        chamadas = self.client._create_conversation.await_args_list
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(chamadas[0].args[1], "CLAUDE_4")
        self.assertEqual(chamadas[1].args[1], "GEMINI")

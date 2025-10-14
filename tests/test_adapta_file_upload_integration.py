import os
import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, skipIf

# Garante que o diretório src esteja no PYTHONPATH para importações locais
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import settings  # noqa: E402
from generators.adapta.client import AdaptaClient  # noqa: E402
from generators.adapta.claude_opus_generator import ClaudeOpusGenerator  # noqa: E402


def _has_valid_credentials() -> bool:
    try:
        cookies = settings.adapta_cookies_str
        session_id = settings.adapta_session_id
    except Exception:
        return False

    return bool(cookies and session_id and "fake" not in cookies.lower())


@skipIf(not _has_valid_credentials(), "Credenciais reais do Adapta.one não configuradas.")
class TestAdaptaFileUploadIntegration(IsolatedAsyncioTestCase):
    """Teste de integração que faz upload e exclusão reais via AdaptaClient."""

    async def asyncSetUp(self) -> None:
        self.cookies = settings.adapta_cookies_str
        self.session_id = settings.adapta_session_id
        self.client = AdaptaClient(
            cookies_str=self.cookies,
            session_id=self.session_id,
        )

        self.generator = ClaudeOpusGenerator(
            cookies_str=self.cookies,
            session_id=self.session_id,
        )

    async def asyncTearDown(self) -> None:
        if self.client and self.client.client and not self.client.client.is_closed:
            await self.client.client.aclose()
        if self.generator and self.generator.client and self.generator.client.client and not self.generator.client.client.is_closed:
            await self.generator.client.client.aclose()

    async def test_upload_and_delete_requirements_file(self) -> None:
        requirements_path = Path(__file__).resolve().parents[1] / "requirements.txt"
        self.assertTrue(requirements_path.exists(), "Arquivo requirements.txt não encontrado.")

        uploaded_data = await self.client.upload_arquivo(str(requirements_path))
        self.assertIsNotNone(uploaded_data, "Upload retornou None.")

        file_id = uploaded_data.get("id")
        self.assertIsNotNone(file_id, "Resposta do upload não contém ID do arquivo.")
        self.assertEqual(
            uploaded_data.get("fileName"),
            "requirements.txt",
            "Nome do arquivo retornado não corresponde.",
        )

        messages = [
            {
                "role": "user",
                "content": "Quantas dependências existem no arquivo enviado?",
            }
        ]

        try:
            resposta_modelo = await self.generator.call_model_with_messages(
                messages,
                file_ids=[uploaded_data],
            )
            self.assertIsNotNone(resposta_modelo, "Modelo não retornou resposta.")
        finally:
            delete_status = await self.client.excluir_arquivo(file_id)
            self.assertIsNotNone(delete_status, "Resposta de exclusão está vazia.")

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from unittest import IsolatedAsyncioTestCase, skipIf

# Garante que o diretório src esteja no PYTHONPATH para importações locais
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import settings  # noqa: E402
from generators_v2.adapta.client import AdaptaClientV2  # noqa: E402


def _has_valid_credentials() -> bool:
    try:
        login = settings.adapta_login
        password = settings.adapta_password
    except Exception:
        return False
    return bool(login and password and "fake" not in login.lower())


@skipIf(not _has_valid_credentials(), "Credenciais reais do Adapta.one nao configuradas.")
class TestAdaptaClient2MainFlow(IsolatedAsyncioTestCase):
    """Teste de integracao que replica o fluxo do main usando as funcoes reais."""

    async def asyncSetUp(self) -> None:
        self._teste_path = Path("teste.txt")
        self._original_bytes: Optional[bytes] = None
        if self._teste_path.exists():
            self._original_bytes = self._teste_path.read_bytes()
        else:
            self._teste_path.parent.mkdir(parents=True, exist_ok=True)
        self._teste_path.write_text("Conteudo de teste para Adapta.\nLinha 2.", encoding="utf-8")

    async def asyncTearDown(self) -> None:
        if self._original_bytes is None:
            try:
                self._teste_path.unlink()
            except FileNotFoundError:
                pass
        else:
            self._teste_path.write_bytes(self._original_bytes)

    async def test_replicated_main_flow_integration(self) -> None:
        buffer = io.StringIO()
        events: List[Tuple[str, str]] = []
        chat_ids: List[str] = []
        uploaded_path: Optional[str] = None
        removal_response: Optional[Dict[str, object]] = None

        with redirect_stdout(buffer):
            async with AdaptaClientV2() as client:
                result = await client.simulate_login()
                masked = {
                    key: value if len(value) <= 10 else f"{value[:4]}...{value[-4:]}"
                    for key, value in result.cookies.items()
                }
                print(f"Session ID: {result.session_id}")
                print(f"Cookies coletados: {masked}")

                local_file = Path("teste.txt")
                uploaded: Dict[str, object]

                if local_file.exists():
                    try:
                        uploaded = await client.upload_arquivo(str(local_file))
                        uploaded_path = uploaded.get("path") if isinstance(uploaded, dict) else None
                        print(f"Upload concluido para {uploaded_path}")
                    except Exception as exc:
                        print(f"Falha ao enviar teste.txt: {exc}")
                        uploaded = {}
                else:
                    print("Arquivo teste.txt nao encontrado; utilizando arquivo de referencia padrao.")
                    uploaded = {}

                pergunta = "quantos topicos tem o manual"
                print("\n--- Streaming em tempo real ---")

                try:
                    stream = await client.call_model(pergunta, files=[uploaded], isStream=True)
                    async for kind, trecho in stream:
                        events.append((kind, trecho))
                        if kind == "thought":
                            print("\n\n\nPensando...\n\n\n")
                            print(trecho, end="", flush=True)
                            print("\n\n\nPensamento Concluido\n\n\n")
                        elif kind == "answer":
                            print(trecho, end="", flush=True)
                except Exception as exc:
                    self.fail(f"Falha durante o streaming de chat: {exc}")

                stream_chat_id = client.last_chat_id
                if stream_chat_id:
                    chat_ids.append(stream_chat_id)
                    print(f"Chat ID (stream): {stream_chat_id}")

                if uploaded_path:
                    try:
                        removal_response = await client.excluir_arquivo(uploaded_path)
                        print(f"\nArquivo remoto teste.txt removido: {removal_response}")
                    except Exception as exc:
                        self.fail(f"Nao foi possivel remover teste.txt: {exc}")

                await client.logout()
                print("\nLogout concluido.")

        captured = buffer.getvalue()
        self.assertIn("Session ID:", captured)
        self.assertIn("Cookies coletados:", captured)
        self.assertIn("Logout concluido.", captured)

        answer_chunks = [text for kind, text in events if kind == "answer" and text.strip()]
        self.assertTrue(answer_chunks, "Nenhuma resposta foi recebida do modelo.")

        if uploaded_path:
            self.assertIsNotNone(removal_response)
            self.assertTrue(removal_response.get("success", False))

        if chat_ids:
            self.assertTrue(all(isinstance(cid, str) and cid for cid in chat_ids))

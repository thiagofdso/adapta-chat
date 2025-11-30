"""Script simples para testar upload e chamada usando o gerador Claude 4.5 (v2).

Fluxo:
- faz login via AdaptaClientV2 (embutido no generator);
- envia o arquivo local ``teste.txt``;
- chama o modelo com o arquivo anexado;
- exibe a resposta e remove o arquivo remoto;
- encerra a sessão.
"""

import asyncio
from pathlib import Path

from generators_v2.adapta.claude_45_sonnet_generator import Claude45SonnetGenerator


async def main() -> None:
    arquivo_local = Path("teste.txt")
    if not arquivo_local.exists():
        raise FileNotFoundError(f"Arquivo local não encontrado: {arquivo_local}")

    generator = Claude45SonnetGenerator()

    try:
        # Login automático ocorre na primeira chamada que exige autenticação.
        upload_info = await generator.client.upload_arquivo(str(arquivo_local))
        print(f"Upload concluído: {upload_info}")

        mensagens = [{"role": "user", "content": "Leia o arquivo enviado e faça um resumo curto."}]
        resposta = await generator.call_model_with_messages(
            mensagens,
            files=[upload_info],  # o client v2 espera dict com path/url/filename/size/mediaType
            stream=False,
        )
        print("\nResposta do modelo:\n")
        print(resposta)

    finally:
        # Remove o arquivo remoto se possível e encerra a sessão.
        try:
            caminho_remoto = upload_info.get("path") if "upload_info" in locals() else None
            if caminho_remoto:
                await generator.client.excluir_arquivo(caminho_remoto)
                print(f"Arquivo remoto removido: {caminho_remoto}")
        except Exception as exc:  # noqa: BLE001 - log simples de limpeza
            print(f"Não foi possível remover o arquivo remoto: {exc}")

        try:
            await generator.client.logout()
        except Exception as exc:  # noqa: BLE001
            print(f"Falha ao encerrar sessão: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

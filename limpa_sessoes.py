import asyncio

from generators_v2.adapta.client import AdaptaClientV2

PROCESS_DELAY_SECONDS = 0.15


async def main() -> None:
    async with AdaptaClientV2() as client:
        sessions = await client.list_active_sessions()
        if not sessions:
            print("Nenhuma sessão encontrada. Verifique suas credenciais do Adapta.")
            return

        total = len(sessions)
        print(f"Total de sessões encontradas: {total}")

        for index, session in enumerate(sessions, start=1):
            session_id = session.get("id")
            if not session_id:
                print(f"[{index}/{total}] Sessão sem ID detectada, ignorando.")
                continue

            try:
                status = await client.fix_session(session_id)
                print(f"[{index}/{total}] Sessão: {session_id} | Status: {status}")
            except Exception as exc:  # noqa: BLE001 - logging simples em script utilitário
                print(f"[{index}/{total}] Sessão: {session_id} | Erro: {exc}")

            await asyncio.sleep(PROCESS_DELAY_SECONDS)

    print("\nProcessamento concluído.")


if __name__ == "__main__":
    asyncio.run(main())

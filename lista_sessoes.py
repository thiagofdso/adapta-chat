import asyncio

from generators_v2.adapta.client import AdaptaClientV2


async def main() -> None:
    async with AdaptaClientV2() as client:
        sessions = await client.list_active_sessions()
        if not sessions:
            print("Nenhuma sessão encontrada. Verifique suas credenciais do Adapta.")
            return

        total = len(sessions)
        print(f"Total de sessões encontradas: {total}")

        for index, session in enumerate(sessions, start=1):
            session_id = session.get("id", "<sem-id>")
            status = session.get("status", "desconhecido")
            last_active = session.get("last_active_at") or session.get("last_active")
            expire_at = session.get("expire_at")
            print(
                f"[{index}/{total}] Sessão: {session_id} | status={status} | "
                f"último uso={last_active or '-'} | expira={expire_at or '-'}"
            )


if __name__ == "__main__":
    asyncio.run(main())

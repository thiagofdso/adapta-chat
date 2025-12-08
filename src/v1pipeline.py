"""Shim para rodar o pipeline original usando generators v1 (GPT/Claude/Gemini).

Necessário porque o pipeline v2 chama `call_model_with_messages(..., files=...)`
enquanto os generators v1 aceitam apenas `file_ids`. Aqui criamos wrappers
compatíveis que aceitam `files`, extraem ids e delegam para os generators v1.
"""

from __future__ import annotations

import asyncio
import sys
import types

from generators.adapta.claude_generator import ClaudeGenerator
from generators.adapta.gpt_generator import GPTGenerator
from generators.adapta.gemini_generator import GeminiGenerator


def _extract_file_ids(files_payload):
    ids = []
    for item in files_payload or []:
        if not isinstance(item, dict):
            continue
        file_id = (
            item.get("id")
            or item.get("fileId")
            or item.get("file_id")
            or item.get("fileKey")
            or item.get("path")
            or item.get("filePathOnStorage")
        )
        if file_id:
            ids.append(file_id)
    return ids or None


class Claude45Shim(ClaudeGenerator):
    async def call_model_with_messages(self, messages, *args, files=None, **kwargs):
        file_ids = _extract_file_ids(files)
        return await super().call_model_with_messages(messages, file_ids=file_ids, **kwargs)


class GPT5Shim(GPTGenerator):
    async def call_model_with_messages(self, messages, *args, files=None, **kwargs):
        file_ids = _extract_file_ids(files)
        return await super().call_model_with_messages(messages, file_ids=file_ids, **kwargs)


class Gemini3ProShim(GeminiGenerator):
    async def call_model_with_messages(self, messages, *args, files=None, **kwargs):
        file_ids = _extract_file_ids(files)
        return await super().call_model_with_messages(messages, file_ids=file_ids, **kwargs)

# Cria módulos fakes para satisfazer imports do pipeline original (v2).
claude_mod = types.ModuleType("generators_v2.adapta.claude_45_sonnet_generator")
claude_mod.Claude45SonnetGenerator = Claude45Shim
sys.modules["generators_v2.adapta.claude_45_sonnet_generator"] = claude_mod

gpt_mod = types.ModuleType("generators_v2.adapta.gpt_5_generator")
gpt_mod.GPT5Generator = GPT5Shim
sys.modules["generators_v2.adapta.gpt_5_generator"] = gpt_mod

gemini_mod = types.ModuleType("generators_v2.adapta.gemini_3_pro_preview_generator")
gemini_mod.Gemini3ProPreviewGenerator = Gemini3ProShim
sys.modules["generators_v2.adapta.gemini_3_pro_preview_generator"] = gemini_mod

# Importa o pipeline original (que agora usará os generators v1 via shim acima)
import pipeline as v2_pipeline  # noqa: E402


async def main():
    await v2_pipeline.main()


if __name__ == "__main__":
    asyncio.run(main())

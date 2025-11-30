"""Gemini 3 Pro Preview generator backed by AdaptaClientV2."""

from pathlib import Path
from typing import Optional

from generators_v2.base import BaseContentGenerator
from generators_v2.adapta.client import AdaptaClientV2


class Gemini3ProPreviewGenerator(BaseContentGenerator):
    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        *,
        client: Optional[AdaptaClientV2] = None,
    ) -> None:
        super().__init__(model_name="GEMINI_3_PRO_PREVIEW", prompts_dir=prompts_dir, client=client)

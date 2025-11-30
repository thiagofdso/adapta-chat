"""One Pro generator backed by AdaptaClientV2."""

from pathlib import Path
from typing import Optional

from generators_v2.base import BaseContentGenerator
from generators_v2.adapta.client import AdaptaClientV2


class OneProGenerator(BaseContentGenerator):
    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        *,
        client: Optional[AdaptaClientV2] = None,
    ) -> None:
        super().__init__(model_name="ONE_PRO", prompts_dir=prompts_dir, client=client)

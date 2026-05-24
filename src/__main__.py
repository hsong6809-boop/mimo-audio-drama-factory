"""MiMo 有声剧工厂 - CLI 入口"""

import sys

from loguru import logger

from .pipeline.orchestrator import main


def run():
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
    )
    main()


if __name__ == "__main__":
    run()

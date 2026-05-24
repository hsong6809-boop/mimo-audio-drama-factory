"""主编排器

负责整个流水线的调度、状态管理、断点续传。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from ..utils.config import get, PROJECT_ROOT
from ..utils.mimo_client import MiMoClient
from ..agents.scriptwriter import ScriptWriter
from ..tts.voice_designer import VoiceDesigner
from ..tts.synthesizer import TTSSynthesizer
from ..audio.composer import AudioComposer
from ..audio.quality_checker import QualityChecker


# ── 状态管理 ──────────────────────────────────────────────

def _state_path(output_dir: Path) -> Path:
    return output_dir / "pipeline_state.json"


def _load_state(output_dir: Path) -> dict:
    p = _state_path(output_dir)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"phase": "init", "completed_steps": []}


def _save_state(output_dir: Path, state: dict):
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(_state_path(output_dir), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── 主编排器 ──────────────────────────────────────────────

class Orchestrator:
    """
    有声剧生成流水线编排器

    Phase 1: 题材 → 结构化剧本 JSON
    Phase 2: 剧本 → 带声纹信息的剧本
    Phase 3: 声纹剧本 → 音频片段
    Phase 4: 音频片段 → 完整有声剧
    Phase 5: 质量闭环
    """

    def __init__(self, output_dir: str | Path | None = None):
        if output_dir is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_dir = PROJECT_ROOT / "output" / date_str
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化所有组件
        self.client = MiMoClient()
        self.writer = ScriptWriter(self.client)
        self.voice_designer = VoiceDesigner(self.client)
        self.synthesizer = TTSSynthesizer(self.client)
        self.composer = AudioComposer()
        self.checker = QualityChecker()

        # 配置日志
        log_file = self.output_dir / "pipeline.log"
        logger.add(str(log_file), rotation="10 MB", level="DEBUG")

    def run(
        self,
        genre: str,
        num_episodes: int | None = None,
        num_characters: int | None = None,
        resume: bool = True,
    ) -> dict:
        """执行完整流水线"""
        state = _load_state(self.output_dir) if resume else {"phase": "init", "completed_steps": []}

        logger.info(f"{'='*60}")
        logger.info(f"有声剧工厂启动 | 题材: {genre}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info(f"{'='*60}")

        # ── Phase 1: 文本生成 ──
        script = None
        if "script_generated" not in state["completed_steps"]:
            logger.info("[Phase 1] 开始生成剧本...")
            script = self.writer.generate_full_script(
                genre=genre,
                num_episodes=num_episodes,
                num_characters=num_characters,
            )

            script_path = self.output_dir / "script.json"
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            logger.info(f"剧本已保存: {script_path}")

            state["completed_steps"].append("script_generated")
            state["script_path"] = str(script_path)
            _save_state(self.output_dir, state)
        else:
            script_path = Path(state.get("script_path", self.output_dir / "script.json"))
            with open(script_path, "r", encoding="utf-8") as f:
                script = json.load(f)
            logger.info(f"[Phase 1] 从文件恢复: {script_path}")

        # ── Phase 2: 声纹设计 ──
        voice_map = None
        if "voice_design_done" not in state["completed_steps"]:
            logger.info("[Phase 2] 开始声纹设计...")
            voice_map = self.voice_designer.design_all(script.get("characters", {}))

            voice_path = self.output_dir / "voice_map.json"
            with open(voice_path, "w", encoding="utf-8") as f:
                json.dump(voice_map, f, ensure_ascii=False, indent=2)
            logger.info(f"声纹映射已保存: {voice_path}")

            state["completed_steps"].append("voice_design_done")
            state["voice_path"] = str(voice_path)
            _save_state(self.output_dir, state)
        else:
            voice_path = Path(state.get("voice_path", self.output_dir / "voice_map.json"))
            with open(voice_path, "r", encoding="utf-8") as f:
                voice_map = json.load(f)
            logger.info(f"[Phase 2] 从文件恢复: {voice_path}")

        # ── Phase 3: 语音合成 ──
        audio_index = None
        if "tts_done" not in state["completed_steps"]:
            logger.info("[Phase 3] 开始语音合成...")
            audio_index = self.synthesizer.synthesize_script(
                script=script,
                voice_map=voice_map,
                output_dir=self.output_dir,
            )

            index_path = self.output_dir / "audio_index.json"
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(audio_index, f, ensure_ascii=False, indent=2)
            logger.info(f"音频索引已保存: {index_path}")

            state["completed_steps"].append("tts_done")
            state["audio_index_path"] = str(index_path)
            _save_state(self.output_dir, state)
        else:
            index_path = Path(state.get("audio_index_path", self.output_dir / "audio_index.json"))
            with open(index_path, "r", encoding="utf-8") as f:
                audio_index = json.load(f)
            logger.info(f"[Phase 3] 从文件恢复: {index_path}")

        # ── Phase 4: 音频编排 ──
        composed_paths = []
        if "audio_composed" not in state["completed_steps"]:
            logger.info("[Phase 4] 开始音频编排...")
            composed_paths = self.composer.compose_all(
                audio_index=audio_index,
                script=script,
                output_dir=self.output_dir,
            )

            state["completed_steps"].append("audio_composed")
            state["composed_paths"] = composed_paths
            _save_state(self.output_dir, state)
        else:
            composed_paths = state.get("composed_paths", [])
            logger.info(f"[Phase 4] 从状态恢复: {len(composed_paths)} 集已编排")

        # ── Phase 5: 质量检查 ──
        if "quality_checked" not in state["completed_steps"]:
            logger.info("[Phase 5] 开始质量检查...")

            script_check = self.checker.check_script(script)

            audio_checks = []
            for ep_num, paths in audio_index.items():
                check = self.checker.check_audio_episode(paths)
                audio_checks.append(check)

            report = self.checker.generate_report(script_check, audio_checks)
            report_path = self.output_dir / "quality_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"质检报告: {report_path}")

            state["completed_steps"].append("quality_checked")
            _save_state(self.output_dir, state)

        # ── 完成 ──
        state["phase"] = "done"
        state["finished_at"] = datetime.now().isoformat()
        _save_state(self.output_dir, state)

        logger.info(f"{'='*60}")
        logger.info(f"流水线完成！")
        logger.info(f"剧本: 《{script.get('title', '未知')}》")
        logger.info(f"集数: {script.get('num_episodes', 0)}")
        logger.info(f"角色: {len(script.get('characters', {}))}")
        logger.info(f"{'='*60}")

        return {
            "title": script.get("title"),
            "episodes": script.get("num_episodes"),
            "characters": len(script.get("characters", {})),
            "output_dir": str(self.output_dir),
            "script_path": str(self.output_dir / "script.json"),
            "audio_dir": str(self.output_dir / "audio"),
            "composed": len(composed_paths),
        }


# ── CLI 入口 ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="MiMo 有声剧工厂")
    parser.add_argument("--genre", "-g", required=True, help="题材（如：仙侠、都市、悬疑）")
    parser.add_argument("--episodes", "-e", type=int, default=None, help="集数（默认10）")
    parser.add_argument("--characters", "-c", type=int, default=None, help="角色数（默认5）")
    parser.add_argument("--output", "-o", default=None, help="输出目录")
    parser.add_argument("--fresh", action="store_true", help="不续传，从头开始")

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")

    orchestrator = Orchestrator(output_dir=args.output)
    result = orchestrator.run(
        genre=args.genre,
        num_episodes=args.episodes,
        num_characters=args.characters,
        resume=not args.fresh,
    )

    print(f"\n✅ 完成！")
    print(f"   《{result['title']}》")
    print(f"   {result['episodes']}集 | {result['characters']}个角色")
    print(f"   音频: {result['composed']}集已编排")
    print(f"   输出: {result['output_dir']}")


if __name__ == "__main__":
    main()

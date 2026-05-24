"""质量检查器

负责：文本质检 + 音频质检 + 角色一致性检查
"""

import json
from pathlib import Path

from loguru import logger

from ..utils.config import get


class QualityChecker:
    """有声剧质量检查"""

    def __init__(self):
        self.config = get("quality") or {}
        self.min_words = self.config.get("min_words_per_segment", 5)
        self.max_words = self.config.get("max_words_per_segment", 200)
        self.max_silence_ms = self.config.get("max_silence_ms", 5000)
        self.max_rewrite = self.config.get("auto_rewrite_max_attempts", 3)

    def check_script(self, script: dict) -> dict:
        """
        检查剧本质量

        Returns:
            {
                "passed": bool,
                "issues": [...],
                "stats": {...}
            }
        """
        issues = []
        stats = {
            "total_episodes": 0,
            "total_segments": 0,
            "total_chars": 0,
            "characters_used": set(),
        }

        for ep in script.get("episodes", []):
            ep_num = ep.get("episode", 0)
            stats["total_episodes"] += 1

            for seg in ep.get("segments", []):
                stats["total_segments"] += 1
                text = seg.get("text", "")
                stats["total_chars"] += len(text)

                # 字数检查
                if len(text) < self.min_words:
                    issues.append({
                        "level": "warning",
                        "episode": ep_num,
                        "message": f"段落过短 ({len(text)}字): {text[:20]}...",
                    })

                if len(text) > self.max_words:
                    issues.append({
                        "level": "warning",
                        "episode": ep_num,
                        "message": f"段落过长 ({len(text)}字): {text[:20]}...",
                    })

                # 角色出场统计
                if seg.get("type") == "dialogue":
                    char = seg.get("character", "")
                    if char:
                        stats["characters_used"].add(char)

                # 情感标注检查
                if seg.get("type") == "dialogue" and not seg.get("emotion"):
                    issues.append({
                        "level": "info",
                        "episode": ep_num,
                        "message": f"对话段落缺少情感标注: {text[:30]}...",
                    })

        # 角色一致性检查
        defined_chars = set(script.get("characters", {}).keys())
        used_chars = stats["characters_used"]
        undefined = used_chars - defined_chars
        if undefined:
            issues.append({
                "level": "error",
                "message": f"剧本中使用了未定义的角色: {undefined}",
            })

        unused = defined_chars - used_chars
        if unused:
            issues.append({
                "level": "info",
                "message": f"以下角色未在剧本中出场: {unused}",
            })

        stats["characters_used"] = list(stats["characters_used"])

        passed = not any(i["level"] == "error" for i in issues)

        logger.info(
            f"剧本质检: {'✅ 通过' if passed else '❌ 不通过'} | "
            f"{stats['total_episodes']}集 {stats['total_segments']}段 "
            f"{stats['total_chars']}字 | {len(issues)} 个问题"
        )

        return {
            "passed": passed,
            "issues": issues,
            "stats": stats,
        }

    def check_audio_episode(self, audio_paths: list[str]) -> dict:
        """检查单集音频质量"""
        from pydub import AudioSegment

        issues = []
        total_duration = 0

        for path in audio_paths:
            try:
                audio = AudioSegment.from_file(path)
                duration_ms = len(audio)
                total_duration += duration_ms

                # 静音检测
                if duration_ms < 500:
                    issues.append({
                        "level": "warning",
                        "file": path,
                        "message": f"音频过短 ({duration_ms}ms)",
                    })

                # 音量检测
                if audio.dBFS < -40:
                    issues.append({
                        "level": "warning",
                        "file": path,
                        "message": f"音量过低 ({audio.dBFS:.1f} dBFS)",
                    })
                elif audio.dBFS > -3:
                    issues.append({
                        "level": "warning",
                        "file": path,
                        "message": f"音量过高 ({audio.dBFS:.1f} dBFS)",
                    })

            except Exception as e:
                issues.append({
                    "level": "error",
                    "file": path,
                    "message": f"音频加载失败: {e}",
                })

        return {
            "passed": not any(i["level"] == "error" for i in issues),
            "issues": issues,
            "total_duration_s": round(total_duration / 1000, 1),
        }

    def generate_report(self, script_check: dict, audio_checks: list[dict]) -> str:
        """生成质检报告"""
        lines = [
            "# 有声剧质检报告",
            "",
            "## 剧本检查",
            f"- 状态: {'✅ 通过' if script_check['passed'] else '❌ 不通过'}",
            f"- 集数: {script_check['stats']['total_episodes']}",
            f"- 段落数: {script_check['stats']['total_segments']}",
            f"- 总字数: {script_check['stats']['total_chars']}",
            "",
        ]

        if script_check["issues"]:
            lines.append("### 剧本问题")
            for issue in script_check["issues"]:
                lines.append(f"- [{issue['level']}] {issue['message']}")
            lines.append("")

        lines.append("## 音频检查")
        for i, ac in enumerate(audio_checks, 1):
            lines.append(
                f"- 第{i}集: {'✅' if ac['passed'] else '❌'} "
                f"时长 {ac['total_duration_s']}s | "
                f"{len(ac['issues'])} 个问题"
            )

        report = "\n".join(lines)
        logger.info("质检报告已生成")
        return report

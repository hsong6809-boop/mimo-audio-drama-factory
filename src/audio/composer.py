"""音频编排器

负责：音频片段 → 完整有声剧（拼接 + BGM + 后期处理）
"""

from pathlib import Path

from loguru import logger

from ..utils.config import get


class AudioComposer:
    """音频编排与后期处理"""

    def __init__(self):
        self.config = get("audio") or {}
        self.silence_seg_ms = self.config.get("silence_between_segments_ms", 300)
        self.silence_char_ms = self.config.get("silence_between_characters_ms", 500)
        self.silence_scene_ms = self.config.get("silence_between_scenes_ms", 1000)
        self.bgm_fade_in = self.config.get("bgm_fade_in_ms", 2000)
        self.bgm_fade_out = self.config.get("bgm_fade_out_ms", 2000)
        self.target_loudness = self.config.get("target_loudness_lufs", -16)

    def compose_episode(
        self,
        audio_paths: list[str],
        script: dict,
        episode_num: int,
        output_dir: Path,
    ) -> str:
        """
        编排单集音频

        Args:
            audio_paths: 该集所有音频片段路径
            script: 完整剧本（用于获取段落信息）
            episode_num: 集数
            output_dir: 输出目录

        Returns:
            最终音频文件路径
        """
        from pydub import AudioSegment

        logger.info(f"编排第 {episode_num} 集: {len(audio_paths)} 个片段")

        # 获取该集的段落信息
        episode = None
        for ep in script.get("episodes", []):
            if ep.get("episode") == episode_num:
                episode = ep
                break

        if not episode:
            logger.error(f"找不到第 {episode_num} 集的剧本信息")
            return ""

        segments = episode.get("segments", [])
        final_audio = AudioSegment.empty()

        for i, (audio_path, seg_info) in enumerate(zip(audio_paths, segments)):
            try:
                segment_audio = AudioSegment.from_file(audio_path)
            except Exception as e:
                logger.warning(f"加载片段失败 {audio_path}: {e}")
                continue

            # 添加段落间静音
            if i > 0:
                prev_seg = segments[i - 1] if i - 1 < len(segments) else {}
                curr_seg = seg_info

                # 根据场景变化决定静音时长
                silence_ms = self._get_silence_duration(prev_seg, curr_seg)
                final_audio += AudioSegment.silent(duration=silence_ms)

            final_audio += segment_audio

        # 导出
        output_path = output_dir / f"episode_{episode_num:03d}.wav"
        final_audio.export(
            str(output_path),
            format="wav",
            parameters=["-ar", "24000", "-ac", "1"],
        )

        logger.info(
            f"第 {episode_num} 集编排完成: {output_path} "
            f"(时长 {len(final_audio) / 1000:.1f}s)"
        )
        return str(output_path)

    def _get_silence_duration(self, prev_seg: dict, curr_seg: dict) -> int:
        """根据前后段落类型决定静音时长"""
        prev_type = prev_seg.get("type", "")
        curr_type = curr_seg.get("type", "")

        # 场景切换（旁白→对话 或 对话→旁白 且角色不同）
        if prev_type != curr_type:
            return self.silence_scene_ms

        # 同类型对话，角色切换
        if curr_type == "dialogue":
            prev_char = prev_seg.get("character", "")
            curr_char = curr_seg.get("character", "")
            if prev_char != curr_char:
                return self.silence_char_ms

        # 默认段落间静音
        return self.silence_seg_ms

    def add_bgm(
        self,
        episode_audio_path: str,
        bgm_path: str,
        output_path: str,
        bgm_volume: float = -15.0,
    ) -> str:
        """为单集添加背景音乐"""
        from pydub import AudioSegment

        logger.info(f"添加 BGM: {bgm_path}")

        episode = AudioSegment.from_file(episode_audio_path)
        bgm = AudioSegment.from_file(bgm_path)

        # 循环 BGM 以匹配音频时长
        episode_len = len(episode)
        if len(bgm) < episode_len:
            loops = (episode_len // len(bgm)) + 1
            bgm = bgm * loops
        bgm = bgm[:episode_len]

        # 调整 BGM 音量
        bgm = bgm + bgm_volume

        # 渐入渐出
        bgm = bgm.fade_in(self.bgm_fade_in).fade_out(self.bgm_fade_out)

        # 混音
        mixed = episode.overlay(bgm)

        # 导出
        mixed.export(
            output_path,
            format="wav",
            parameters=["-ar", "24000", "-ac", "1"],
        )

        logger.info(f"BGM 混音完成: {output_path}")
        return output_path

    def normalize_loudness(self, audio_path: str, output_path: str | None = None) -> str:
        """响度标准化（EBU R128）"""
        from pydub import AudioSegment

        if output_path is None:
            output_path = audio_path

        audio = AudioSegment.from_file(audio_path)

        # 简单的峰值归一化
        target_dbfs = self.target_loudness
        change = target_dbfs - audio.dBFS
        normalized = audio.apply_gain(change)

        normalized.export(
            output_path,
            format="wav",
            parameters=["-ar", "24000", "-ac", "1"],
        )

        logger.debug(f"响度标准化: {audio_path} → {output_path}")
        return output_path

    def compose_all(
        self,
        audio_index: dict,
        script: dict,
        output_dir: Path,
    ) -> list[str]:
        """编排所有集"""
        composed = []
        for ep_num, paths in audio_index.items():
            out_path = self.compose_episode(
                audio_paths=paths,
                script=script,
                episode_num=ep_num,
                output_dir=output_dir,
            )
            if out_path:
                composed.append(out_path)
        return composed

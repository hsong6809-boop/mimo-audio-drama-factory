"""TTS 语音合成引擎

负责：带情感标注的文本 → 音频片段
"""

import hashlib
import json
from pathlib import Path

from loguru import logger

from ..utils.config import get
from ..utils.mimo_client import MiMoClient


class TTSSynthesizer:
    """MiMo TTS 合成器"""

    def __init__(self, client: MiMoClient):
        self.client = client
        self.config = get("tts") or {}
        self.sample_rate = self.config.get("sample_rate", 24000)
        self.output_format = self.config.get("output_format", "wav")

    def synthesize_segment(
        self,
        text: str,
        voice_id: str,
        emotion: str = "neutral",
        pace: str = "normal",
        output_path: Path | None = None,
    ) -> Path:
        """
        合成单个段落的音频

        Args:
            text: 文本内容
            voice_id: 音色 ID
            emotion: 情感（calm/excited/sad/angry/solemn/fearful/happy/neutral）
            pace: 语速预设（slow/normal/fast）
            output_path: 输出路径（None 则自动生成）

        Returns:
            音频文件路径
        """
        if output_path is None:
            # 自动生成路径：用内容哈希避免重复合成
            text_hash = hashlib.md5(f"{voice_id}:{emotion}:{text}".encode()).hexdigest()[:12]
            output_path = Path(f"cache/{voice_id}_{emotion}_{text_hash}.{self.output_format}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果已缓存，直接返回
        if output_path.exists():
            logger.debug(f"缓存命中: {output_path.name}")
            return output_path

        # 构建 TTS 参数
        params = self._build_params(voice_id, emotion, pace)

        logger.debug(f"TTS 合成: [{emotion}] {text[:30]}...")

        # 调用 MiMo TTS API
        audio_data = self.client.tts(
            text=text,
            voice_id=voice_id,
            speed=params["speed"],
            pitch=params["pitch"],
            volume=params["volume"],
        )

        # 写入文件
        with open(output_path, "wb") as f:
            f.write(audio_data)

        logger.debug(f"TTS 输出: {output_path} ({len(audio_data)} bytes)")
        return output_path

    def _build_params(self, voice_id: str, emotion: str, pace: str) -> dict:
        """构建 TTS 参数"""
        emotion_params = self.config.get("emotion_params", {})
        emo = emotion_params.get(emotion, emotion_params.get("neutral", {}))

        speed = emo.get("speed", 1.0)
        pitch = emo.get("pitch", 0)
        volume = emo.get("volume", 0.85)

        # pace 覆盖
        pace_map = {"slow": 0.8, "normal": 1.0, "fast": 1.2}
        speed *= pace_map.get(pace, 1.0)

        return {
            "speed": round(max(0.5, min(1.5, speed)), 2),
            "pitch": pitch,
            "volume": round(max(0.3, min(1.3, volume)), 2),
        }

    def synthesize_script(
        self,
        script: dict,
        voice_map: dict,
        output_dir: Path,
    ) -> dict:
        """
        合成完整剧本的所有音频

        Args:
            script: 结构化剧本
            voice_map: 角色声纹映射 {name: voice_config}
            output_dir: 音频输出目录

        Returns:
            音频文件索引 {episode_num: [audio_path, ...]}
        """
        audio_dir = output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        index = {}
        total = sum(len(ep.get("segments", [])) for ep in script.get("episodes", []))
        done = 0

        for ep in script.get("episodes", []):
            ep_num = ep.get("episode", 0)
            ep_dir = audio_dir / f"ep_{ep_num:03d}"
            ep_dir.mkdir(parents=True, exist_ok=True)

            ep_audio = []
            for i, seg in enumerate(ep.get("segments", [])):
                text = seg.get("text", "")
                if not text.strip():
                    continue

                # 确定音色和情感
                if seg.get("type") == "dialogue":
                    char_name = seg.get("character", "")
                    voice_cfg = voice_map.get(char_name, {})
                    voice_id = voice_cfg.get("voice_id", "v_young_male_hero")
                    emotion = seg.get("emotion", "neutral")
                else:
                    # 旁白用默认音色
                    voice_id = "v_young_male_hero"
                    emotion = seg.get("emotion", "calm")

                pace = seg.get("pace", "normal")
                out_path = ep_dir / f"seg_{i:03d}.{self.output_format}"

                audio_path = self.synthesize_segment(
                    text=text,
                    voice_id=voice_id,
                    emotion=emotion,
                    pace=pace,
                    output_path=out_path,
                )
                ep_audio.append(str(audio_path))
                done += 1

            index[ep_num] = ep_audio
            logger.info(f"第 {ep_num} 集合成完成: {len(ep_audio)} 段 ({done}/{total})")

        return index

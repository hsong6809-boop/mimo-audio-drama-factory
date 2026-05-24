"""角色声纹设计器

负责：角色属性 → 声纹参数 → 音色样本 → 声纹库存储
"""

import json
from pathlib import Path

import numpy as np
from loguru import logger

from ..utils.config import get


# ── 基础音色库 ──────────────────────────────────────────────
# 每个基础音色有明确的适用范围，用于快速匹配

BASE_VOICES = [
    {
        "id": "v_young_male_hero",
        "label": "青年男主",
        "gender": "male",
        "age": "young",
        "style": "heroic",
        "base_pitch": 0,
        "base_speed": 1.0,
    },
    {
        "id": "v_young_female_hero",
        "label": "青年女主",
        "gender": "female",
        "age": "young",
        "style": "bright",
        "base_pitch": 3,
        "base_speed": 1.0,
    },
    {
        "id": "v_middle_male_authority",
        "label": "中年权威",
        "gender": "male",
        "age": "middle",
        "style": "authoritative",
        "base_pitch": -1,
        "base_speed": 0.9,
    },
    {
        "id": "v_elderly_male_wise",
        "label": "老年智者",
        "gender": "male",
        "age": "elderly",
        "style": "wise",
        "base_pitch": -2,
        "base_speed": 0.8,
    },
    {
        "id": "v_young_female_gentle",
        "label": "温柔女声",
        "gender": "female",
        "age": "young",
        "style": "gentle",
        "base_pitch": 2,
        "base_speed": 0.9,
    },
    {
        "id": "v_middle_female_mature",
        "label": "成熟女声",
        "gender": "female",
        "age": "middle",
        "style": "mature",
        "base_pitch": 1,
        "base_speed": 0.95,
    },
    {
        "id": "v_young_male_friendly",
        "label": "阳光少年",
        "gender": "male",
        "age": "young",
        "style": "friendly",
        "base_pitch": 1,
        "base_speed": 1.1,
    },
    {
        "id": "v_child_neutral",
        "label": "童声",
        "gender": "male",
        "age": "child",
        "style": "cute",
        "base_pitch": 5,
        "base_speed": 1.05,
    },
]


class VoiceDesigner:
    """角色声纹设计与管理"""

    def __init__(self, mimo_client=None):
        self.client = mimo_client
        self.config = get("voice_db") or {}
        self.tts_config = get("tts") or {}
        self.emotion_params = self.tts_config.get("emotion_params", {})

    def match_base_voice(self, character: dict) -> dict:
        """根据角色属性匹配最接近的基础音色"""
        gender = character.get("gender", "male")
        age = character.get("age", "young")
        personality = character.get("personality", "").lower()

        # 评分匹配
        best_score = -1
        best_voice = BASE_VOICES[0]

        for voice in BASE_VOICES:
            score = 0
            if voice["gender"] == gender:
                score += 3
            if voice["age"] == age:
                score += 2

            # 性格关键词加权
            style = voice["style"]
            if style in personality or personality in style:
                score += 1

            if score > best_score:
                best_score = score
                best_voice = voice

        logger.debug(
            f"音色匹配：{character['name']} → {best_voice['label']} "
            f"(score={best_score})"
        )
        return best_voice

    def design_voice(self, character: dict) -> dict:
        """
        为角色设计完整声纹配置

        Returns:
            {
                "voice_id": "v_young_male_hero",
                "base_voice": {...},
                "params": {"pitch": 0, "speed": 1.0, "volume": 0.85},
                "emotion_overrides": {...}
            }
        """
        base = self.match_base_voice(character)

        # 根据性格微调参数
        params = self._tune_params(character, base)

        # 为每种情感生成参数覆盖
        emotion_overrides = self._build_emotion_overrides(base, params)

        voice_config = {
            "voice_id": base["id"],
            "base_voice": base,
            "params": params,
            "emotion_overrides": emotion_overrides,
        }

        logger.info(
            f"声纹设计完成：{character['name']} → {base['label']} "
            f"(pitch={params['pitch']}, speed={params['speed']})"
        )
        return voice_config

    def _tune_params(self, character: dict, base: dict) -> dict:
        """根据角色性格微调基础参数"""
        pitch = base["base_pitch"]
        speed = base["base_speed"]
        volume = 0.85

        personality = character.get("personality", "").lower()
        speaking = character.get("speaking_pattern", "").lower()

        # 性格 → 参数微调
        if any(k in personality for k in ["活泼", "开朗", "energetic", "热血"]):
            speed += 0.1
            pitch += 1
            volume = 0.9
        elif any(k in personality for k in ["沉稳", "冷静", "wise", "深沉"]):
            speed -= 0.1
            pitch -= 1
            volume = 0.8
        elif any(k in personality for k in ["温柔", "gentle", "善良"]):
            speed -= 0.05
            volume = 0.75
        elif any(k in personality for k in ["暴躁", "angry", "急躁"]):
            speed += 0.15
            pitch += 2
            volume = 0.95

        # 说话习惯 → 参数微调
        if any(k in speaking for k in ["语速慢", "慢条斯理"]):
            speed -= 0.15
        elif any(k in speaking for k in ["语速快", "快人快语", "直来直去"]):
            speed += 0.15

        return {
            "pitch": max(-5, min(8, pitch)),
            "speed": max(0.6, min(1.4, speed)),
            "volume": max(0.4, min(1.2, volume)),
        }

    def _build_emotion_overrides(self, base: dict, base_params: dict) -> dict:
        """为每种情感构建参数覆盖"""
        overrides = {}
        for emotion, emo_cfg in self.emotion_params.items():
            overrides[emotion] = {
                "pitch": base_params["pitch"] + emo_cfg.get("pitch", 0),
                "speed": round(base_params["speed"] * emo_cfg.get("speed", 1.0), 2),
                "volume": round(base_params["volume"] * emo_cfg.get("volume", 1.0), 2),
                "pause_ms": emo_cfg.get("pause_ms", 100),
            }
        return overrides

    def design_all(self, characters: dict) -> dict:
        """为所有角色设计声纹"""
        voice_map = {}
        for name, char in characters.items():
            voice_map[name] = self.design_voice(char)
        return voice_map

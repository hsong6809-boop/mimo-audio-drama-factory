"""剧本创作 Agent

负责：题材分析 → 角色设计 → 剧情大纲 → 逐集详细剧本
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from ..utils.mimo_client import MiMoClient
from ..utils.config import get


# ── 系统提示词 ──────────────────────────────────────────────

SYSTEM_ROLE = """你是一位专业的有声剧编剧。你的任务是根据用户给定的题材，创作适合有声剧形式的剧本。

关键要求：
1. 对话要口语化，适合朗读，避免书面语
2. 旁白要简洁有画面感，适合声音表达
3. 每个角色的说话风格要有明显区分
4. 情感标注要准确，便于后续 TTS 合成
5. 输出必须是严格的 JSON 格式"""

CHARACTER_DESIGN_PROMPT = """为「{genre}」题材设计 {num} 个角色，要求：

1. 角色之间有明确的关系和冲突
2. 每个角色有独特的说话方式和性格
3. 覆盖不同性别和年龄段

每个角色必须包含以下字段：
- name: 角色名（中文，2-4字）
- gender: "male" 或 "female"
- age: "child" / "young" / "middle" / "elderly"
- personality: 性格描述（一句话）
- voice_style: 声音风格（如"低沉浑厚"、"清脆悦耳"、"沙哑沧桑"）
- speaking_pattern: 说话习惯（如"语速慢，爱用成语"、"直来直去，偶尔爆粗"）
- role: 角色定位（"protagonist" / "antagonist" / "supporting"）

输出 JSON 数组格式，示例：
[
  {{
    "name": "李逍遥",
    "gender": "male",
    "age": "young",
    "personality": "外表玩世不恭，内心重情重义",
    "voice_style": "清朗少年音",
    "speaking_pattern": "爱开玩笑，关键时刻认真",
    "role": "protagonist"
  }}
]"""

OUTLINE_PROMPT = """基于以下角色，为「{genre}」有声剧创作 {episodes} 集的剧情大纲。

角色信息：
{characters}

要求：
1. 故事有明确的主线和高潮
2. 每集结尾有悬念，吸引听众继续
3. 情感起伏合理，有张有弛
4. 适合有声剧形式，场景不要太复杂

每集包含：
- episode: 集数（从1开始）
- title: 集标题
- summary: 剧情摘要（100-200字）
- key_events: 关键事件列表（3-5个）
- emotional_arc: 情感走向（如"平静→紧张→爆发→释然"）
- characters_involved: 本集出场角色名列表

输出 JSON 数组格式。"""

EPISODE_PROMPT = """根据以下信息，创作第 {episode} 集「{title}」的完整剧本。

剧情摘要：{summary}
关键事件：{key_events}
情感走向：{emotional_arc}
出场角色：{characters_involved}

角色设定：
{character_details}

要求：
1. 总字数控制在 {min_words}-{max_words} 字
2. 每个段落必须标注 type（narration 或 dialogue）
3. 对话段落必须标注 character 和 emotion
4. 旁白段落标注 pace（slow / normal / fast）
5. 段落之间逻辑连贯，情感自然过渡
6. 对话要口语化，适合朗读
7. 适当加入环境描写和动作描写

输出 JSON 格式，结构如下：
{{
  "episode": {episode},
  "title": "{title}",
  "segments": [
    {{
      "type": "narration",
      "text": "旁白内容",
      "emotion": "calm",
      "pace": "slow"
    }},
    {{
      "type": "dialogue",
      "character": "角色名",
      "text": "对话内容",
      "emotion": "angry"
    }}
  ]
}}

emotion 可选值：calm, excited, sad, angry, solemn, fearful, happy, neutral
pace 可选值：slow, normal, fast"""


class ScriptWriter:
    """剧本创作 Agent"""

    def __init__(self, client: MiMoClient):
        self.client = client
        self.config = get("script") or {}
        self.words_range = self.config.get("words_per_episode", [2000, 3000])

    def design_characters(self, genre: str, num_characters: int = 5) -> list[dict]:
        """设计角色"""
        logger.info(f"设计角色：{genre} 题材，{num_characters} 个角色")

        prompt = CHARACTER_DESIGN_PROMPT.format(
            genre=genre, num=num_characters
        )
        characters = self.client.generate_json(
            prompt, system=SYSTEM_ROLE, temperature=0.9
        )

        # 兼容：如果返回的是 dict 而不是 list，取第一个值
        if isinstance(characters, dict):
            for v in characters.values():
                if isinstance(v, list):
                    characters = v
                    break

        logger.info(f"设计了 {len(characters)} 个角色：{[c['name'] for c in characters]}")
        return characters

    def generate_outline(
        self, genre: str, characters: list[dict], num_episodes: int = 10
    ) -> list[dict]:
        """生成剧情大纲"""
        logger.info(f"生成剧情大纲：{num_episodes} 集")

        prompt = OUTLINE_PROMPT.format(
            genre=genre,
            episodes=num_episodes,
            characters=json.dumps(characters, ensure_ascii=False, indent=2),
        )
        outline = self.client.generate_json(
            prompt, system=SYSTEM_ROLE, temperature=0.85
        )

        if isinstance(outline, dict):
            for v in outline.values():
                if isinstance(v, list):
                    outline = v
                    break

        logger.info(f"大纲生成完成：{len(outline)} 集")
        return outline

    def write_episode(
        self,
        episode_info: dict,
        characters: list[dict],
        episode_num: int,
    ) -> dict:
        """生成单集详细剧本"""
        logger.info(f"创作第 {episode_num} 集：{episode_info.get('title', '')}")

        # 构建角色详情
        involved_names = episode_info.get("characters_involved", [])
        char_details = [
            c for c in characters if c["name"] in involved_names
        ]
        if not char_details:
            char_details = characters  # fallback：全部角色

        prompt = EPISODE_PROMPT.format(
            episode=episode_num,
            title=episode_info.get("title", f"第{episode_num}集"),
            summary=episode_info.get("summary", ""),
            key_events=json.dumps(
                episode_info.get("key_events", []), ensure_ascii=False
            ),
            emotional_arc=episode_info.get("emotional_arc", ""),
            characters_involved=", ".join(involved_names),
            character_details=json.dumps(
                char_details, ensure_ascii=False, indent=2
            ),
            min_words=self.words_range[0],
            max_words=self.words_range[1],
        )

        episode = self.client.generate_json(
            prompt, system=SYSTEM_ROLE, temperature=0.8
        )

        # 确保结构完整
        episode.setdefault("episode", episode_num)
        episode.setdefault("title", episode_info.get("title", f"第{episode_num}集"))
        episode.setdefault("segments", [])

        seg_count = len(episode["segments"])
        logger.info(f"第 {episode_num} 集完成：{seg_count} 个段落")
        return episode

    def generate_full_script(
        self,
        genre: str,
        num_episodes: int | None = None,
        num_characters: int | None = None,
    ) -> dict:
        """
        一键生成完整剧本

        Args:
            genre: 题材
            num_episodes: 集数（默认从配置读取）
            num_characters: 角色数（默认从配置读取）

        Returns:
            完整剧本 JSON
        """
        num_episodes = num_episodes or self.config.get("default_episodes", 10)
        num_characters = num_characters or self.config.get("default_characters", 5)

        logger.info(
            f"开始创作：{genre} | {num_episodes}集 | {num_characters}角色"
        )

        # Step 1: 设计角色
        characters = self.design_characters(genre, num_characters)

        # Step 2: 生成大纲
        outline = self.generate_outline(genre, characters, num_episodes)

        # Step 3: 逐集创作
        episodes = []
        for i, ep_info in enumerate(outline, 1):
            episode = self.write_episode(ep_info, characters, i)
            episodes.append(episode)

        # 组装完整剧本
        script = {
            "title": self._generate_title(genre),
            "genre": genre,
            "num_episodes": len(episodes),
            "characters": {c["name"]: c for c in characters},
            "episodes": episodes,
        }

        logger.info(
            f"剧本创作完成：《{script['title']}》{len(episodes)}集"
        )
        return script

    def _generate_title(self, genre: str) -> str:
        """让 MiMo 生成一个书名"""
        prompt = f"为一部{genre}有声剧起一个吸引人的名字，只输出书名，不要其他内容。"
        return self.client.generate(prompt, temperature=0.9, max_tokens=50).strip().strip('"').strip("'")

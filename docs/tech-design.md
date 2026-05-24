# 技术设计文档

## 1. 技术选型

### 核心依赖

| 模块 | 技术方案 | 说明 |
|------|---------|------|
| LLM | MiMo 大模型 API | 剧本生成、情感分析、角色设计 |
| TTS | MiMo TTS API | 多角色语音合成 |
| 音频处理 | pydub + FFmpeg | 拼接、混音、格式转换 |
| 音频分析 | librosa | 声纹特征提取、质量检测 |
| 向量数据库 | ChromaDB | 角色声纹库管理 |
| 任务编排 | 自研 Pipeline | 多阶段流水线控制 |
| 配置管理 | PyYAML | 灵活的参数配置 |

### Python 版本

- 最低要求：Python 3.10+
- 推荐版本：Python 3.11

## 2. 模块设计

### 2.1 剧本创作 Agent（scriptwriter.py）

```python
class ScriptWriter:
    """剧本创作 Agent"""

    def __init__(self, mimo_client):
        self.mimo = mimo_client

    def generate_script(
        self,
        topic: str,
        num_episodes: int = 10,
        num_characters: int = 5,
        style: str = "default"
    ) -> dict:
        """
        生成完整剧本

        Args:
            topic: 题材（如"仙侠"、"都市"、"悬疑"）
            num_episodes: 集数
            num_characters: 角色数
            style: 风格（default/romantic/comedy/dark）

        Returns:
            结构化剧本 JSON
        """
        # 1. 生成角色设定
        characters = self._design_characters(topic, num_characters)

        # 2. 生成剧情大纲
        outline = self._generate_outline(topic, characters, num_episodes)

        # 3. 逐集生成详细剧本
        episodes = []
        for ep in range(num_episodes):
            episode = self._generate_episode(
                outline, characters, ep + 1
            )
            episodes.append(episode)

        return {
            "title": self._generate_title(topic),
            "genre": topic,
            "style": style,
            "characters": characters,
            "episodes": episodes
        }

    def _design_characters(self, topic, num):
        """设计角色（含声纹属性）"""
        prompt = f"""
        为{topic}题材设计{num}个角色，每个角色包含：
        - name: 名字
        - gender: male/female
        - age: child/young/middle/elderly
        - personality: 性格关键词
        - voice_style: 声音风格描述
        - speaking_pattern: 说话习惯

        输出 JSON 格式。
        """
        return self.mimo.generate(prompt, response_format="json")

    def _generate_outline(self, topic, characters, num_episodes):
        """生成剧情大纲"""
        prompt = f"""
        基于以下角色，生成{num_episodes}集的剧情大纲：
        角色：{json.dumps(characters, ensure_ascii=False)}

        每集包含：
        - episode_number
        - title
        - key_events: 关键事件列表
        - emotional_arc: 情感走向
        """
        return self.mimo.generate(prompt, response_format="json")

    def _generate_episode(self, outline, characters, ep_num):
        """生成单集详细剧本"""
        prompt = f"""
        根据大纲生成第{ep_num}集的详细剧本。

        要求：
        1. 每个段落标注 type(narration/dialogue)
        2. 对话标注 character 和 emotion
        3. 旁白标注 pace(slow/normal/fast)
        4. 总字数控制在 2000-3000 字

        输出结构化 JSON。
        """
        return self.mimo.generate(prompt, response_format="json")
```

### 2.2 角色声纹设计器（voice_designer.py）

```python
class VoiceDesigner:
    """角色声纹设计与管理"""

    def __init__(self, tts_client, vector_db):
        self.tts = tts_client
        self.db = vector_db

    def design_voice(self, character: dict) -> dict:
        """
        为角色设计声纹

        Args:
            character: 角色属性（gender, age, personality等）

        Returns:
            声纹配置（voice_id, params）
        """
        # 1. 基础音色匹配
        base_voice = self._match_base_voice(character)

        # 2. 微调参数
        params = self._tune_params(character, base_voice)

        # 3. 生成样本音频
        sample = self._generate_sample(base_voice, params)

        # 4. 提取声纹特征
        features = self._extract_features(sample)

        # 5. 存入向量库
        voice_id = self._save_to_db(character, features, params)

        return {
            "voice_id": voice_id,
            "base_voice": base_voice,
            "params": params,
            "sample_path": sample
        }

    def _match_base_voice(self, character):
        """根据属性匹配基础音色"""
        # 查询已有声纹库
        query_features = self._character_to_features(character)
        results = self.db.query(query_features, top_k=3)

        if results and results[0]["score"] > 0.85:
            return results[0]["voice_id"]  # 复用已有音色

        # 否则创建新音色
        return self._create_new_voice(character)

    def _tune_params(self, character, base_voice):
        """微调 TTS 参数"""
        age_map = {
            "child": {"pitch": +4, "speed": 1.1},
            "young": {"pitch": +1, "speed": 1.0},
            "middle": {"pitch": 0, "speed": 0.95},
            "elderly": {"pitch": -2, "speed": 0.85}
        }

        gender_map = {
            "male": {"pitch": -1, "timbre": "deep"},
            "female": {"pitch": +2, "timbre": "bright"}
        }

        params = {
            "base_voice": base_voice,
            "pitch": 0,
            "speed": 1.0,
            "timbre": "neutral"
        }

        # 合并年龄和性别参数
        params.update(age_map.get(character["age"], {}))
        params.update(gender_map.get(character["gender"], {}))

        return params
```

### 2.3 情感 TTS 引擎（emotion_tts.py）

```python
class EmotionTTS:
    """带情感控制的 TTS 引擎"""

    # 情感 → TTS 参数映射
    EMOTION_MAP = {
        "calm":     {"speed": 0.85, "pitch": 0,   "pause": 200,  "volume": 0.8},
        "excited":  {"speed": 1.2,  "pitch": +2,  "pause": 50,   "volume": 1.0},
        "sad":      {"speed": 0.75, "pitch": -1,  "pause": 300,  "volume": 0.6},
        "angry":    {"speed": 1.1,  "pitch": +3,  "pause": 100,  "volume": 1.1},
        "solemn":   {"speed": 0.9,  "pitch": -1,  "pause": 250,  "volume": 0.9},
        "fearful":  {"speed": 1.15, "pitch": +1,  "pause": 150,  "volume": 0.5},
        "joyful":   {"speed": 1.1,  "pitch": +2,  "pause": 80,   "volume": 0.95},
        "tender":   {"speed": 0.8,  "pitch": +1,  "pause": 250,  "volume": 0.7},
    }

    def __init__(self, tts_client):
        self.tts = tts_client

    def synthesize(
        self,
        text: str,
        voice_id: str,
        emotion: str = "calm",
        intensity: float = 0.5,
        pace: str = "normal"
    ) -> str:
        """
        合成带情感的语音

        Args:
            text: 文本内容
            voice_id: 声纹 ID
            emotion: 情感标签
            intensity: 情感强度 (0-1)
            pace: 语速预设 (slow/normal/fast)

        Returns:
            音频文件路径
        """
        # 1. 获取基础参数
        base_params = self.EMOTION_MAP.get(emotion, self.EMOTION_MAP["calm"])

        # 2. 根据强度插值
        params = self._interpolate(base_params, intensity)

        # 3. 应用语速预设
        pace_map = {"slow": 0.85, "normal": 1.0, "fast": 1.15}
        params["speed"] *= pace_map.get(pace, 1.0)

        # 4. 调用 TTS API
        audio_path = self.tts.generate(
            text=text,
            voice_id=voice_id,
            speed=params["speed"],
            pitch=params["pitch"],
            volume=params["volume"]
        )

        # 5. 后处理：添加停顿
        if params["pause"] > 0:
            audio_path = self._add_pause(audio_path, params["pause"])

        return audio_path

    def _interpolate(self, base_params, intensity):
        """根据情感强度插值参数"""
        # intensity=0 时接近中性，intensity=1 时完全表达
        neutral = {"speed": 1.0, "pitch": 0, "pause": 100, "volume": 0.85}

        result = {}
        for key in base_params:
            neutral_val = neutral.get(key, 0)
            emotion_val = base_params[key]
            result[key] = neutral_val + (emotion_val - neutral_val) * intensity

        return result
```

### 2.4 音频编排器（composer.py）

```python
class AudioComposer:
    """音频编排器"""

    def __init__(self, bgm_manager, sfx_manager):
        self.bgm = bgm_manager
        self.sfx = sfx_manager

    def compose_episode(
        self,
        segments: list[dict],
        bgm_style: str = "default"
    ) -> str:
        """
        编排单集音频

        Args:
            segments: 音频片段列表（含文本、角色、情感信息）
            bgm_style: BGM 风格

        Returns:
            完整音频文件路径
        """
        from pydub import AudioSegment

        # 1. 获取 BGM
        bgm_track = self.bgm.get_bgm(bgm_style, duration_estimate=600)

        # 2. 拼接音频片段
        final_audio = AudioSegment.empty()

        for i, seg in enumerate(segments):
            # 段落间静音
            if i > 0:
                pause_ms = 500 if seg["type"] == "dialogue" else 300
                final_audio += AudioSegment.silent(duration=pause_ms)

            # 添加音频片段
            segment_audio = AudioSegment.from_file(seg["audio_path"])
            final_audio += segment_audio

        # 3. 混入 BGM
        final_audio = self._mix_bgm(final_audio, bgm_track)

        # 4. 添加开头结尾
        final_audio = self._add_intro_outro(final_audio)

        # 5. 导出
        output_path = f"output/episode_{segments[0]['episode_num']}.mp3"
        final_audio.export(output_path, format="mp3", bitrate="192k")

        return output_path

    def _mix_bgm(self, voice_audio, bgm_track):
        """混入 BGM（自动调整音量）"""
        from pydub import AudioSegment

        # BGM 音量降低到 20%
        bgm_track = bgm_track - 14  # 约降低 14dB

        # 循环 BGM 以匹配语音长度
        voice_duration = len(voice_audio)
        bgm_track = bgm_track * (voice_duration // len(bgm_track) + 1)
        bgm_track = bgm_track[:voice_duration]

        # 混合
        return voice_audio.overlay(bgm_track)

    def _add_intro_outro(self, audio):
        """添加片头片尾"""
        from pydub import AudioSegment

        intro = AudioSegment.from_file("assets/intro.mp3")
        outro = AudioSegment.from_file("assets/outro.mp3")
        silence = AudioSegment.silent(duration=1000)

        return intro + silence + audio + silence + outro
```

### 2.5 质检模块（quality_check.py）

```python
class QualityChecker:
    """音频质量检测"""

    def __init__(self, tts_client):
        self.tts = tts_client

    def check_episode(self, episode_data: dict) -> dict:
        """
        检测单集质量

        Returns:
            {
                "passed": bool,
                "issues": list,
                "suggestions": list
            }
        """
        issues = []

        # 1. 文本质量检查
        text_issues = self._check_text_quality(episode_data)
        issues.extend(text_issues)

        # 2. 音频质量检查
        audio_issues = self._check_audio_quality(episode_data)
        issues.extend(audio_issues)

        # 3. 角色一致性检查
        consistency_issues = self._check_character_consistency(episode_data)
        issues.extend(consistency_issues)

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "suggestions": self._generate_suggestions(issues)
        }

    def _check_text_quality(self, episode_data):
        """检查文本质量"""
        issues = []

        for seg in episode_data["segments"]:
            # 检查字数
            if len(seg["text"]) < 5:
                issues.append({
                    "type": "text",
                    "severity": "warning",
                    "segment": seg["id"],
                    "message": "文本过短，可能导致 TTS 效果不佳"
                })

            # 检查特殊字符
            if any(c in seg["text"] for c in ["[", "]", "{", "}"]):
                issues.append({
                    "type": "text",
                    "severity": "error",
                    "segment": seg["id"],
                    "message": "文本包含可能干扰 TTS 的特殊字符"
                })

        return issues

    def _check_audio_quality(self, episode_data):
        """检查音频质量"""
        import librosa
        issues = []

        for seg in episode_data["segments"]:
            if "audio_path" not in seg:
                continue

            # 加载音频
            y, sr = librosa.load(seg["audio_path"])

            # 检查音量
            rms = librosa.feature.rms(y=y)[0]
            if rms.mean() < 0.01:
                issues.append({
                    "type": "audio",
                    "severity": "error",
                    "segment": seg["id"],
                    "message": "音频音量过低，可能为静音"
                })

            # 检查时长
            duration = librosa.get_duration(y=y, sr=sr)
            text_len = len(seg["text"])
            expected_duration = text_len * 0.3  # 粗略估计

            if duration < expected_duration * 0.5:
                issues.append({
                    "type": "audio",
                    "severity": "warning",
                    "segment": seg["id"],
                    "message": f"音频时长({duration:.1f}s)与文本长度不匹配"
                })

        return issues

    def _check_character_consistency(self, episode_data):
        """检查角色声纹一致性"""
        # TODO: 实现声纹比对
        return []
```

## 3. 配置文件设计

```yaml
# config/default.yaml

# MiMo API 配置
mimo:
  api_key: "${MIMO_API_KEY}"
  model: "mimo-turbo"
  max_tokens: 4096

# TTS 配置
tts:
  engine: "mimo-tts"
  default_voice: "neutral"
  sample_rate: 24000
  output_format: "mp3"

# 音频配置
audio:
  bitrate: "192k"
  sample_rate: 44100
  channels: 2  # 立体声
  intro_file: "assets/intro.mp3"
  outro_file: "assets/outro.mp3"

# 质量阈值
quality:
  min_text_length: 5
  min_audio_volume: 0.01
  max_duration_ratio: 2.0
  voice_similarity_threshold: 0.85

# 输出配置
output:
  base_dir: "output"
  naming_pattern: "{title}_EP{episode:03d}"
  formats: ["mp3", "wav"]
```

## 4. 依赖清单

```
# requirements.txt

# MiMo SDK
mimo-sdk>=1.0.0

# 音频处理
pydub>=0.25.1
librosa>=0.10.0
soundfile>=0.12.0

# 向量数据库
chromadb>=0.4.0

# 配置管理
pyyaml>=6.0

# 工具
tqdm>=4.65.0
rich>=13.0.0

# 开发依赖
pytest>=7.0.0
black>=23.0.0
```

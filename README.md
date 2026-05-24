# MiMo 多角色有声剧工厂

> 输入一个题材，自动产出带角色配音、背景音效的完整有声剧音频

## 项目概述

本项目基于 MiMo 大模型的文本生成能力和 TTS 语音合成能力，构建一个端到端的有声剧自动生产流水线。用户只需提供题材和基本设定，系统自动完成剧本创作、角色声纹设计、多角色语音合成、音频编排和后期处理，最终输出可直接发布的有声剧音频文件。

## 核心技术栈

- **MiMo 大模型**：剧本生成、角色对话、旁白撰写
- **MiMo TTS**：多角色语音合成、情感控制
- **音频处理**：FFmpeg、pydub、librosa
- **向量数据库**：角色声纹库管理（ChromaDB）
- **任务编排**：多 Agent 协作流水线

## 项目结构

```
mimo-audio-drama-factory/
├── README.md                 # 项目说明
├── docs/                     # 文档
│   ├── architecture.md       # 系统架构
│   ├── tech-design.md        # 技术设计
│   └── roadmap.md            # 开发路线图
├── src/                      # 源代码
│   ├── agents/               # Agent 模块
│   │   ├── scriptwriter.py   # 剧本创作 Agent
│   │   ├── director.py       # 导演 Agent（编排）
│   │   └── quality_check.py  # 质检 Agent
│   ├── tts/                  # TTS 模块
│   │   ├── voice_designer.py # 角色声纹设计
│   │   ├── emotion_tts.py    # 情感 TTS
│   │   └── voice_manager.py  # 声纹库管理
│   ├── audio/                # 音频处理模块
│   │   ├── composer.py       # 音频编排
│   │   ├── bgm_manager.py    # BGM/音效管理
│   │   └── post_process.py   # 后期处理
│   ├── pipeline/             # 流水线编排
│   │   └── orchestrator.py   # 主编排器
│   └── utils/                # 工具函数
├── config/                   # 配置文件
│   └── default.yaml          # 默认配置
├── assets/                   # 资源文件
│   ├── bgm/                  # 背景音乐
│   └── sfx/                  # 音效
├── output/                   # 输出目录
└── tests/                    # 测试
```

## 开发阶段

### Phase 1：基础框架（1-2周）
- [ ] 项目初始化、依赖管理
- [ ] 剧本创作 Agent 基础版
- [ ] MiMo TTS 接口封装
- [ ] 简单的音频拼接

### Phase 2：角色声纹系统（2-3周）
- [ ] 角色属性提取与音色匹配
- [ ] 情感标注与 TTS 参数控制
- [ ] 声纹库管理（一致性校验）

### Phase 3：音频编排（2周）
- [ ] 旁白 + 对话自动拼接
- [ ] BGM/音效智能插入
- [ ] 音频后处理（降噪、均衡）

### Phase 4：质量闭环（1-2周）
- [ ] 自动质检（吞字、断句、串音）
- [ ] 不达标自动重写
- [ ] 用户反馈学习

### Phase 5：产品化（2周）
- [ ] Web UI / 命令行工具
- [ ] 跨设备分发（手机/音箱）
- [ ] 续播功能

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行示例
python -m pipeline.orchestrator --topic "仙侠" --characters 5 --episodes 10
```

## License

MIT

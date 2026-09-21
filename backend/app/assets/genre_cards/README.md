# genre_cards/ 数据来源与许可

本目录 32 张正文题材卡 `.md` 文件直接拷贝自：

- 原项目：oh-story-claudecode
- 路径：`skills/story-long-write/references/genre-prose-cards/*.md`
- 许可：MIT License（Copyright (c) 2025-2026 oh-story-claudecode）

另有题材「反模式 / 节奏策略 / 典型分幕」迁移自：

- 原项目：storyforge
- 路径：`src/lib/ai/genre-metadata.ts`
- 许可：MIT License（Copyright (c) 2026 yuanbw2025）

应用到 `backend/app/services/genre.py` 的注册表。storyforge 未覆盖的题材
（军事 / 体育 / 诸天等），反模式取自本目录对应题材卡的「禁止漂移」段。

保留两份 MIT 版权声明与本次使用；改动集中在 `genre.py` 的加载逻辑，卡片正文未改动。
# builderIO-cardgame

> **這個 repo 的目的:** 用 [BuilderIO/skills](https://github.com/BuilderIO/skills) 的
> **factory skills**(實驗性)來體驗「**Agentic Software Factory**」——
> 讓 AI agent 自主地從需求 → 實作 → PR → 審查,感受高度自動化的軟體開發流程。
> 這是個玩具專案,重點是**流程體驗**,不是遊戲本身。

## 專案內容
一個回合制卡牌 Roguelike 的純邏輯戰鬥引擎(不做畫面),卡牌與技能全部用資料(JSON)定義。
詳細需求見 [`spec.md`](spec.md)。

- 技術棧:**Python + pytest**
- 模型:全部使用 **Haiku**(節省 token 用量)

## Factory skills
位於 `.claude/skills/` 與 `.agents/skills/`(`factory`、`factory-collect`、`factory-ship`、
`factory-review-prs`、`factory-babysit-pr` 等)。
上游說明文件已保存於 [`docs/factory-upstream-README.md`](docs/factory-upstream-README.md)。

## 自主度策略
先讓 agent 自動實作並開 PR;review / approve / merge 先手動,熟悉後再逐步開放。

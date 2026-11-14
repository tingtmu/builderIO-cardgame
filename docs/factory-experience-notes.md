# Agentic Software Factory 體驗筆記

> 日期:2026-11-14 · 專案:builderIO-cardgame(玩具專案)
> 目的:用 BuilderIO 的 factory skills 體驗「高度自動化」的軟體開發流程。

## 一句話結論
從一份粗略的 `spec.md` 開始,到 4 個里程碑全部 merge,**我只在幾個關鍵點給了授權**
(啟動、授權 merge、改成全自動)。其餘的 issue 拆解、實作、測試、開 PR、審查、merge、
清理 worktree 都由 agent 完成。最終 154 個測試全過、CI 綠燈。

## 結果
| 里程碑 | PR | 測試數 | 內容 |
| --- | --- | --- | --- |
| M1 | #5 | 27 | Card/Effect/Status/Unit 資料結構、JSON 載入、3 張範例卡 |
| M2 | #6 | 68 | 回合流程、固定種子可重現、效果依 `EffectKind` 分派 |
| M3 | #7 | 109 | 中毒/虛弱/護盾,行為由 `data/statuses.json` 描述 |
| M4 | #8 | 154 | 資料驅動敵人 AI(循環/加權)、可預告意圖、完整戰鬥重現測試 |

repo:https://github.com/tingtmu/builderIO-cardgame

## 流程是怎麼跑的
1. **安裝**:factory skills 放在 `.claude/skills/`、`.agents/skills/`。
2. **`/factory` 設定**:寫 `.agent-factory/config.yaml`(來源、各動作政策、`skill_prompts`)。
3. **輸入**:把 spec 的 4 個里程碑開成帶 `milestone` 標籤的 GitHub Issues。
4. **實作**:每個 issue 交給一個 Haiku 子 agent,在獨立 git worktree 裡做,
   一個 issue = 一個 branch = 一個 PR(`Closes #N`)。
5. **審查**(`/factory-review-prs`):讀 diff、看 CI、在乾淨 clone 重跑測試、檢查範圍與依賴。
6. **Merge**:條件通過才 squash merge,並用 `--match-head-commit` 鎖定審查過的那個 commit。
7. **接力**:M1 → M2 → M3 → M4,因為彼此有依賴,所以序列執行。

## 自主度:一開始刻意保守,再逐步放開
- 第一版 config:只有 `implement` 與 `publish` 開著,`approve`、`merge`、`reply`、`close`、`deploy` 全部關閉。
- M1 的 PR 由我審查後,**等使用者明確授權**才 merge。
- 使用者說「全自動」後,config 改成條件式 approve/merge:
  - CI 的 `test` 在最新 head 上通過
  - 在乾淨 checkout 重跑 `uv run pytest` 通過
  - 改動在 issue 範圍內、沒有新增依賴
  - 不動 `.agent-factory/` 與不相關的 `.github/`
  - 條件不符就停(hold)
- 原則:**「能修」≠「能回覆/核准/merge/部署」,每個動作各自授權。** 沒寫清楚就是 hold。

## 實際踩到的坑(下次可以先避開)
| 坑 | 原因 / 處理 |
| --- | --- |
| 把子 agent 的 worktree 當成內嵌 repo commit 進去 | 在 `.gitignore` 加 `.claude/worktrees/`,重新 commit |
| 推送 `.github/workflows/ci.yml` 被拒 | `gh` token 缺 `workflow` 權限;需使用者執行 `gh auth refresh -h github.com -s workflow` |
| 新 workflow 對舊 PR 不會自動跑 | 用 `gh pr update-branch <N>` 讓 PR 重新觸發 CI |
| `git push` 要輸入帳密 | 執行 `gh auth setup-git` 讓 git 使用 gh 的憑證 |
| `uv init` 把個人 email 寫進 `pyproject.toml` | 子 agent 自行移除 authors;merge 前我再 grep 檢查 |
| commit 署名不一致(Sonnet / Haiku) | 提示詞給的署名不一致;下次在 config 的 `skill_prompts` 統一寫死 |
| zsh 的 glob 讓 `grep --include=*.toml` 失敗 | 指令要加引號,檢查結果要確認真的有執行 |

## 這次學到的
- **審查要自己驗證,不要照單全收子 agent 的報告。** 每次都在乾淨 clone 重跑測試,抓得到「本地能過、乾淨環境不能過」的問題。
- **`--match-head-commit`** 讓 merge 只作用在審查過的那個 commit,避免審查後被偷換內容。
- **資料驅動的設計**(卡牌、狀態、敵人 AI 都在 JSON)讓 agent 的改動範圍小、風險低、好測試。
- **固定亂數種子**讓「同種子 → 同戰鬥」成為可自動驗證的規格,是很好的 agent 驗收標準。
- **有依賴的任務要序列執行**;沒有依賴的才適合平行。
- **「全自動」其實是「由某個 session 接力」**:session 關掉就停。要真正無人值守,必須在 host 建立排程 job
  (本次沒有建立)。

## 這次沒有驗證到的
- 沒有排程 job、沒有 `/factory-watchdog`、`/factory-recover`、`/factory-lookback`。
- 輸入只有我們手寫的 issue,沒有真實的玩家回報、崩潰或遙測。
- 沒有 `reply`(回覆人)、`close`、`deploy`。
- 審查者和實作者是同一類模型,自己審自己,測試若寫得不嚴就抓不到。

## 開發者的經驗(來自影片,憑使用者記憶整理,未逐字核對)
1. **用 monorepo 對 factory 更好**——agent 在同一處就能看到相關程式、測試與設定。
2. **工廠的效果高度取決於輸入品質**——先把 telemetry、客戶回饋管道、錯誤可見性建好。
3. **分開 beta 與 production**——內部使用者都用 beta,beta 永遠與 main 同步;問題先在 beta 修,
   每天更新一次,所以容易回滾。(也就是:merge ≠ 發布。)
4. **從小處開始**——先接一個輸入來源,切出一小組可以交給 agent 的事,例如
   「清楚的錯誤訊息、可驗證、只做高信心的」,再用 YAML 調整語氣與範圍。
   限制:「做對你有效的事,不要做無效的事。」

對照本次:我們是單一 repo(符合 1);輸入是手寫 issue,品質高但不是真實訊號(第 2 點沒被考驗);
merge 進 main 就算完成,沒有 beta/production 之分(第 3 點沒做);第 4 點「從小開始」我們有照做,
先手動、再放開 merge。

## 如果要上 Steam,會發生什麼(摘要)
- 現在只有戰鬥引擎,遊戲本體(UI、存檔、整合)還沒有。
- factory 的價值會在有真實訊號後才顯現:崩潰修復、資料檔小改動、`lookback` 找復發問題。
- 風險:玩家回報是不可信的外部輸入、「修好」不等於「玩家覺得好」(平衡與設計要留給人)、
  自動 merge 可能傷到存檔相容性、代表你回覆玩家有公關風險。
- 建議分級:
  - **自動**:有重現步驟的崩潰、資料檔小改動、文件
  - **自動修但人 merge**:動到戰鬥規則的程式碼
  - **只通知人**:平衡、新功能、玩家要求、回覆玩家、發布到 Steam
- 發布永遠與 merge 分開,最多讓 agent 準備好 build。

## 下次可以試的方向
1. 建立排程 job,讓 collect → review → merge 每天自己跑一次。
2. 接入真實訊號(例如對玩家開放的 issue 範本、崩潰回報),觀察分流品質。
3. 加上 beta 分支或 beta 環境,練習「merge ≠ 發布」。
4. 試 `/factory-lookback` 與 `/factory-human-digest`,感受決策清單的效果。
5. 把審查換成不同模型或獨立的檢查,降低「自己審自己」的盲點。

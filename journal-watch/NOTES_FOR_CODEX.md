# 给 CodeX 的注意事项 —— journal-watch（每日论文速递）

> 写给以后要改这套工具的 CodeX。先读完这份再动手，里面几条规则是 2026-09-24 至 11-06 用真实漏推/误推换来的，碰坏了会直接反映在每天早上 08:00 的推送里。

## 一、这是什么

- 这是「每日论文速递」的工具链：每天扫描 13 本期刊（Nature、Science、JACS、Joule、Nature Energy 等）的电池/能源材料新论文，过滤后推送到用户的论文旁聊。
- 来源：OpenClaw skill（journal watch），2026-09-24 转成云电脑上的定时任务。
- 链路：RSS / Crossref 抓取 → 关键词过滤 → SQLite 入库去重 → 每天 08:00 推送新增。
- 仓库：github.com/dengw666/journal-watcher（main 分支）。本地工作目录在云电脑 `~/workspace/journal-watch/journal-watch`。

## 二、每天是怎么跑的（不要改调用顺序）

定时任务 `journal-watch-daily-digest`，每天 08:00，依次执行：

```bash
cd ~/workspace/journal-watch/journal-watch
export OPENCLAW_SKILL_VENV_ROOT=$HOME/workspace/journal-watch/venvs
python3 bin/journal-watch scan --quiet
python3 bin/journal-watch backfill --days 3 --quiet
python3 bin/journal-watch recent --mark-sent --hours 26
```

- `scan`：抓 RSS/API，覆盖过去约 7–14 天。
- `backfill --days 3`：走 Crossref 按 ISSN 兜底，补 RSS 滚出或单日失败漏掉的论文。
- `recent --mark-sent --hours 26`：只推新增，推完标记已发送。
- 依赖装在 `~/workspace/journal-watch/venvs`（外部固定目录），**不要放进仓库**。

## 三、不要碰坏的规则（核心）

1. **过滤是强/弱分级（2026-11-06 改的，别改回单关键词放行）**
   - 任一强关键词命中即放行，或至少 2 个弱关键词才放行。
   - 单个通用词（electrolyte / electrode / cathode / energy storage / charge transfer 等）不再放行——回填曾因此误入库淀粉样蛋白、果蝇、X 射线激光等论文。
   - 强关键词清单在 `config/topics.yaml` 的 `include_keywords` 里（含 CO2、电还原、析氧、氨合成、燃料电池等）；弱关键词集合是 `src/filter.py` 里的 `GENERIC_KEYWORDS`。
   - `Nature Energy` 是全收（`PASSTHROUGH_JOURNALS`），不走关键词过滤。
2. **Crossref 回填按发表日期过滤（2026-11-01 修的 bug）**
   - `src/sources/crossref.py` 用的是 `from-pub-date`，之前错写成 `from-index-date` 会漏论文。不要改回去。
3. **回填一次拉 500 条（`src/app.py` 里 `rows=500`）**
   - Nat Commun 3 天总量约 143 条，`rows=100` 会被截断漏论文。
4. **评论类文章要核查被评的原论文**
   - 推送 News & Views / 评论类文章时，核查其点评的原论文是否已推送；未推送要说明并补推原论文标题与 DOI，**不编摘要**。
5. **只推新增，不回填旧论文**
   - 用户 2026-10-31 拍板：只做 scan + 3 天回填，不补推旧论文。
6. **改过滤规则后必须跑回归验证**
   - 标准：2026-10-28 至 11-05 已推的 18 篇非 Nature Energy 论文必须全部仍通过；验证脚本回放当日候选，确认没有已推论文被新规则剔除。

## 四、数据库是运行状态，不要动它

- `data/journal_watch.db` 是本地运行状态（已入库论文、已推送标记、去重依据），**不要提交到仓库、不要删除、不要跨机器复制**。
- `__pycache__/`、`venvs/`、`.db-shm` / `.db-wal` 也不要提交。

## 五、常见故障与口径

- RSS 403 / 抓取中断是常态（如 Science、Science Advances、JACS 常返回 403，Joule 偶发中断），不是 bug；源失败时在日志里记下来即可。
- Nature Energy 的 RSS 只列最近约 8 条，发表时没扫到、恢复时已滚出 feed 是已知漏推根因，靠 `backfill --days 3` 兜底，不要加长 RSS 回溯。
- 推送缺口要如实声明，**不要硬凑、不要编论文、不要编 DOI 和摘要**。一篇论文 DOI 查不到、全网搜不到时，结论就是「尚未正式发表」。

## 六、与 iOS PDF 翻译 App 的关系（整合设计，见下）

用户想把每日文献接进正在做的 Duo 双栏 PDF 翻译 App：每天既能看到文献更新列表，又能点开阅读翻译。架构原则：

1. **搜索留在服务端，不要搬进 App**
   - iOS 没有 cron；`BGAppRefreshTask` 的执行时间由系统决定、不保证每天跑、每次只有约 30 秒，免费签名下更不可靠；Shortcuts 自动化同样不稳定。App 里做定时搜索是死路。
   - 搜索不需要 LLM：RSS + Crossref + 关键词过滤就够了，DeepSeek 只负责翻译，不要拿 DeepSeek 做搜索。
2. **App 只消费每日 feed**
   - 定时任务每天产出一个 JSON（如 `feed/daily-YYYY-MM-DD.json`），字段：标题、期刊、发表日期、DOI、摘要链接、开放获取 PDF 链接（如有）、是否已读。
   - 建议把 feed 提交到本仓库（或单独的数据分支），App 走 `raw.githubusercontent.com` 拉取——不用另搭服务器，自带版本历史。
   - 不要在 App 里直连数据库，不要把 `.db` 文件打进 App。
3. **点开一篇论文后**
   - 有开放获取 PDF 的，下载进阅读器再翻译；付费墙的只给 DOI 链接和摘要，**不要绕过付费墙下载**。

## 七、不要做的事

- 不要把 API Key、密钥、token 写进仓库、代码或配置文件（2026-11-09 有新闻：GitHub 上 10 万多份泄露文件含真实密钥，教训就是别把密钥放仓库）。
- 不要改推送格式与编号协议：旁聊里用户报编号（如「1/2/4」）即表示要对应论文的摘要与 DOI，格式变了会打断这个约定。
- 不要把测试数据、个人文件提交进仓库。
- 改完先在本地跑一遍 `scan → backfill --days 3 → recent`（不加 `--mark-sent` 先看输出），确认无误再让定时任务跑。

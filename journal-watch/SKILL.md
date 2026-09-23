---
name: journal-watch
description: >
  Monitor new papers from Nature, Science, JACS, Joule, ChemRxiv and 8 other
  selected journals in battery and energy materials research. Scan RSS feeds
  and APIs daily, filter by keywords, deduplicate, and generate digests with
  DOI links. Use when the user asks about new papers, wants a daily or detailed
  research digest, or asks what's new in batteries/energy materials.
  Triggers: new papers, latest research, journal watch, paper digest, scan
  journals, what's new in batteries.
---

# Journal Watch

扫描一组学术期刊，发现电池与能源材料新论文。自动从 DOI landing page 补充摘要。

## 安装与依赖布局

所有命令在 `{baseDir}` 下执行。

首次运行会自动把依赖安装到**外部固定目录**，默认是：

```bash
~/.openclaw/venvs/journal-watch
```

这样 skill 本体目录保持轻量，分发/同步时**不要携带 `.venv`**。
如需统一改外部依赖根目录，可设置环境变量：

```bash
OPENCLAW_SKILL_VENV_ROOT=/some/path
```

**核心规则：每次用户询问论文，都必须先执行 `scan --quiet`。** scan 从 13 个期刊抓取 RSS/API 数据存入本地数据库（覆盖过去约 7-14 天的论文）。不 scan 就没有数据。

```bash
cd {baseDir}
```

### 第一步：扫描 + 展示列表

```bash
python3 bin/journal-watch scan --quiet        # 抓取 + 自动补摘要
python3 bin/journal-watch digest              # 输出当天论文列表
```

把 digest 输出展示给用户。格式为按期刊分组的编号列表。
只展示当天（北京时间）有论文的期刊。然后问用户对哪几篇感兴趣。

**注意：展示给用户的论文列表，必须每篇单独一行，包含序号和期刊名，例如：**
```
1.【Nature】论文标题
2.【JACS】论文标题
```
**严禁**把所有论文用顿号/分号连接成一段输出。

### 第二步：展示详情

用户说出编号后：

```bash
python3 bin/journal-watch show 1,3,5          # 返回选中论文详情
```

展示：期刊、发表日期、DOI链接、作者、摘要、匹配关键词。

### 查看指定日期

用户说"3月17号的论文"：

```bash
python3 bin/journal-watch scan --quiet              # 必须先扫描，否则数据库为空
python3 bin/journal-watch digest --date 2026-03-17
python3 bin/journal-watch show 1,2 --date 2026-03-17
```

**重要：无论用户问哪天的论文，都必须先执行 `scan --quiet`。** scan 会抓取 RSS 中所有论文（通常覆盖过去 7-14 天），存入数据库后再按日期查询。如果跳过 scan，数据库为空，digest 会返回"暂无新论文"。

## 所有命令

| 命令 | 说明 |
|------|------|
| `init` | 初始化数据库（仅首次） |
| `scan` | 抓取 RSS/API + 自动补摘要 |
| `digest` | 当天论文列表（北京时间） |
| `digest --date YYYY-MM-DD` | 指定日期论文列表 |
| `show 1,3,5` | 选中论文的详情 |
| `show 1,3 --date YYYY-MM-DD` | 指定日期论文详情 |
| `backfill` | Crossref 补充（可选） |

## 依赖

见 `requirements.txt`：feedparser, requests, python-dateutil, beautifulsoup4, lxml, pyyaml, pytest

## 注意事项

- JACS 摘要受 ACS 限制无法获取（RSS/Crossref/landing page 均不提供）
- Nature/Joule/Science 等期刊可通过 DOI landing page 补充完整摘要
- 每次 HTTP 请求后自动等待 ≥1s，遵守爬虫礼仪
- 去重由 DOI + normalized_title + URL 三级保证
- 时间按北京时间（UTC+8）计算"今天"

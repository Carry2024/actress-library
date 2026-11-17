# 女友资料库 · Actress Library

基于 [Gfriends](https://github.com/gfriends/gfriends) 的头像索引，扩展演员公开资料、生日、身高、三围、别名、履历和独立 TOP 榜。中文文档，Python 标准库实现。

**首版是可运行的资料库与更新工具，不是已经补全所有演员的全量数据库。** 已核对 3 位演员：miru、明里つむぎ、吉高寧々。当前没有已核实的外部 TOP 榜，个人榜为空，绝不虚构名次。

## Emby 中文演员名、头像与资料

使用 [主 Emby 同步说明](docs/EMBY.md)。运行 `python3 scripts/emby_sync.py plan` 先扫描；API Key 仅在本机输入。

## 直接查看

- [演员资料目录](docs/CATALOG.md)
- [可检索浏览页](docs/index.html)：下载后通过下面的本地服务打开；GitHub 文件预览不执行网页。
- [结构化资料](docs/catalog.json)
- [TOP 数据目录](data/rankings)
- [来源与使用范围](NOTICE.md)

## 包含哪些内容

| 内容 | 首版状态 |
| --- | --- |
| 姓名、稳定 ID、人工核对别名 | 已支持；不同写法不直接合并身份 |
| 生日、身高、三围、罩杯、出生地 | 有来源才填；每个字段保存来源与核对日期 |
| 履历 | 支持出道、改名、获奖等带日期事件；人工核对录入 |
| 头像 | 自动匹配 Gfriends 现有索引；保存候选链接，未冒充人工身份确认 |
| TOP | 支持个人排序、外部榜单的来源/周期/日期/指标；外部榜需导入核实快照 |
| 自动更新 | C-more 两个首批资料页和三位演员的 Gfriends 头像引用 |
| 变更记录 | 自动更新前保留字段旧值；抓取失败不把资料清空 |
| 可视浏览 | 姓名搜索、生日排序、资料与履历详情、分榜查看 |

吉高寧々官方页在本次运行环境直连失败，初始资料经网页检索核对，`refresh_source` 暂为 `null`；不会把手工资料宣称为自动更新。

上游索引的十万余张图片不等于十万位已核实演员。资料库数量以 `data/actors` 为准。

## 本地运行 / NAS

要求 Python 3.11 或更新版本，无第三方依赖。在仓库根目录执行：

```bash
python3 scripts/library.py validate
python3 scripts/library.py build
python3 -m http.server 8765 --bind 127.0.0.1 --directory docs
```

浏览器打开 `http://127.0.0.1:8765`。NAS 远程访问可在 SSH 客户端添加端口转发，或按自己的局域网访问策略部署；本项目不修改现有容器、Emby 或原始媒体文件。

刷新已配置来源：

```bash
python3 scripts/library.py refresh
```

GitHub Actions 提供手动刷新，也配置为每周一北京时间 10:20 更新。只有上传到 GitHub 且 Actions 启用后才会运行。源码校验不联网；刷新失败时不提交数据。计划任务可能延迟，外部站点也可能限制访问。

## 如何补充演员

1. 参考 `data/actors/miru.json`，新建稳定 ID 的 JSON 文件，例如 `actor-name.json`。
2. 填官方来源 URL 与实际核对日期；个人资料字段采用 `{value, source, checked_at}`。未知字段设 `null`。
3. 别名仅加入核对过的艺名，来源记录在 `sources` 和 `notes` 中，切勿因名字相似合并演员。
4. `refresh_source` 指向已支持的来源 ID 才启用自动刷新；现有解析器支持 C-more 与 T-POWERS 的资料格式，需可从运行环境访问。否则保持 `null`。
5. 需要保留手动值时，在字段对象增加 `"locked": true`；自动刷新会跳过。
6. 运行校验与构建，再提交到仓库。官网更名时脚本会停止该次刷新，需要人工核对。

## TOP 榜怎么用

`data/rankings/personal.json` 是自己的偏好榜。`entries` 逐行填入 `{"rank": 1, "actor_id": "miru"}` 等记录，名次必须唯一，不代表外部平台评价。

外部榜需先核对来源，再准备 JSON：

```json
{
  "id": "platform-monthly",
  "title": "平台演员月榜",
  "kind": "external",
  "as_of": "2026-11-17",
  "period": "2026-11",
  "metric": "填写来源真实公布的排名指标",
  "source_url": "https://example.org/replace-with-actual-source",
  "entries": []
}
```

以上为格式模板，不是真实榜单。演员 ID 必须已存在于资料库；原站若未提供评分，不自行补造。

```bash
python3 scripts/library.py import-ranking /path/to/verified-ranking.json
```

同一个榜按日期保存快照，不覆盖历史。首版未接入外部榜自动采集，不将 README 中的某个历史获奖冒充当前人气排名。

## GitHub 创建

建议先建私有仓库。若在自己的电脑使用 GitHub CLI，解压后进入此目录执行：

```bash
gh auth login
git init -b main
git add .
git commit -m 'Create sourced actress library'
gh repo create actress-library --private --source=. --remote=origin --push
```

账号已有同名仓库时更换新仓库名；不要覆盖已有项目。Git 提示作者身份缺失时，使用你自己的 GitHub 提交姓名和邮箱配置。

## 与 NGi / Emby 的关系

这是独立资料库。它**不能直接填入 NGi 的自定义演员映射仓库输入框**；该输入需要 NGi 兼容的 `mapping_actor.xml`，本项目没有导出该格式。现在提供独立的主 Emby 人员同步脚本，见 [Emby 使用说明](docs/EMBY.md)：先扫描预览，再按人员 ID 小批量写入。当前覆盖三位演员，尚未在用户 NAS 实测。

## 检验

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：页面拦截/错人不写入、完整生日与单位、头像顺序与多图、榜单来源/演员 ID、刷新失败保留旧数据。

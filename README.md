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
| 自动更新 | C-more 两个首批资料页、三位演员的 Gfriends 头像引用、演员映射底表 |
| NGi 映射表 | 根目录 `mapping_actor.xml`，完整底表 + 个人中文名 |
| 中文名头像 | `data/avatars/index.json` 对照表 + `scripts/avatars.py fetch` 本机下载，交给 Inputer 导入 |
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

## 仓库可见性

本仓库需保持**公开**：NGi 匿名读取 main 分支的 `mapping_actor.xml`，设置页没有填写令牌的位置，私有仓库无法通过“验证地址”。仓库只存资料、引用链接和映射表，不存图片文件；Emby API Key、`emby-plan.json`、`emby-backups/` 已在 `.gitignore` 中排除，切勿提交。

## NGi 自定义演员映射仓库

根目录的 `mapping_actor.xml` 供 NGi 读取。在 NGi“设置 → 元数据”开启“自定义演员映射仓库”，地址填：

```
https://github.com/Carry2024/actress-library
```

点击“验证地址”，通过后保存，在任务空闲时重启后端/容器加载（见 [NGi Wiki：元数据翻译与映射](https://github.com/li-peifeng/NGi/wiki/元数据翻译与映射)）。

开启后 NGi 只读这一份文件、停用默认表的自动更新，所以它必须是**完整演员表**，不能只有自己改过的几位。生成方式：

- 底表：`data/mapping/base_mapping_actor.xml`，默认取自 [li-peifeng/Jav-Actors-Mapping](https://github.com/li-peifeng/Jav-Actors-Mapping) 的精简表（NGi 作者维护；是否等同 NGi 内置默认表未经官方确认）。
- 个人中文名：`data/emby-names.json` 的 `display_name` 写入对应条目的 `zh_cn`，`match_names` 补入 `keyword`。可选 `zh_tw`、`jp` 字段覆盖繁体名和日文名。只靠共用别名匹配到多位演员时会报错，不猜测。

```bash
python3 scripts/mapping.py build        # 修改 emby-names.json 后重新生成
python3 scripts/mapping.py check        # 校验格式并确认已同步（Actions 每次推送都会跑）
python3 scripts/mapping.py update-base  # 更新底表并重新生成
python3 scripts/mapping.py update-base --file /path/to/mapping_actor.xml  # 改用从 NGi 容器拷出的默认表
```

每周的刷新 Action 也会更新底表；新底表条数比旧表少 10% 以上时停止，不覆盖。

格式：UTF-8，根节点 `<actor>`，每位演员一条 `<a zh_cn="" zh_tw="" jp="" keyword="" />`，keyword 用英文逗号分隔、首尾不加逗号。NGi 实际校验规则未公开，以“验证地址”结果为准。

NGi 输出语言选简体中文时，Emby 里的演员名就是 `zh_cn`。中文名建议只通过本映射表统一；`emby_sync.py` 直接改 Emby 人员名，若与 NGi 写入 NFO 的名字不一致，可能出现重复人员，建议只用它补简介和头像。

## 中文名头像（配合 Gfriends Inputer）

NGi 按本映射表把演员写成中文名后，Gfriends 里大多数头像仍按日文名存放，直接用 Inputer 只能匹配一部分。`data/avatars/index.json` 把映射表里每位演员的中文、繁体、日文名对到 Gfriends 的图片（只用该演员独有的名字，共用别名不参与），由每周刷新 Action 更新。

在能访问 Emby 的电脑或 NAS 上：

```bash
python3 scripts/avatars.py fetch --dry-run   # 先统计：询问 Emby 地址和 API Key，只读
python3 scripts/avatars.py fetch             # 下载 Emby 中缺头像演员的头像到 ./Avatar/，文件名为 Emby 中的演员名
```

然后在 Gfriends Inputer 的 `Config.ini` 把 `Local_Path` 设为该 `Avatar/` 的完整路径（结尾带 `/`），运行 Inputer 完成裁剪和导入。`Avatar/` 已加入 `.gitignore`，不会被提交。

- `--no-ai-fix` 使用未经 AI 放大的原图；`--names-file names.txt` 不连 Emby，按每行一个名字下载。
- 下载明细写入 `Avatar/avatar-report.json`，包括无匹配的演员名单，可据此人工补图。
- 匹配基于名字，不做人脸核验；同名不同人的情况由映射表的别名规则控制。

## 与 Emby 的关系

主 Emby 人员同步脚本见 [Emby 使用说明](docs/EMBY.md)：先扫描预览，再按人员 ID 小批量写入。当前覆盖三位演员，尚未在用户 NAS 实测。

## 检验

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：页面拦截/错人不写入、完整生日与单位、头像顺序与多图、榜单来源/演员 ID、刷新失败保留旧数据。

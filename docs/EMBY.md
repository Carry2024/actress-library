# 主 Emby 演员资料同步

这是独立的 API 同步工具。NGi 演员映射仓库请看 README 的“NGi 自定义演员映射仓库”一节。

## 首版覆盖范围

| 公开艺名 | 本库采用的中文显示名 | 无头像时 |
| --- | --- | --- |
| miru / 坂道みる | 坂道美琉 | 尝试 C-more 官方个人页头像 |
| 明里つむぎ | 明里紬 | 尝试 C-more 官方个人页头像 |
| 吉高寧々 | 吉高宁宁 | 暂不自动填图，保留已有头像 |

中文显示名是可编辑的个人偏好，配置在 `data/emby-names.json`。以上只有三位，不是全库人物映射。扫描将列出其他人员，后续据真实库存补资料。现有头像不替换，同一演员多个人员 ID 不自动合并。

## 运行

在 GitHub 仓库点 Code → Download ZIP。解压到 NAS 或能连接主 Emby 的电脑，进入解压后的目录。需要 Python 3.11+。

```bash
python3 scripts/emby_sync.py plan
```

按提示输入**主 Emby** 的地址和管理 API Key。地址示例格式 `http://NAS地址:主Emby端口/emby`；请填实际端口，不能用 Emby2 的 8097。API Key 只在本机隐藏输入，不写入仓库、命令历史或报告。多个管理员账号时另选 User ID。

`plan` 只读扫描，不修改 Emby，生成 `emby-plan.json`：

- `changes`：唯一匹配且有资料的候选，含人员 ID、原名、拟修改字段、头像地址。
- `ambiguous`：重复人员 ID 或别名冲突，暂不处理。
- `unmatched`：尚无可靠资料的人员，仅记录 ID、名字和有无头像。

预览文件包含自己的媒体库人员清单，保留在本机，不上传到公开仓库。先看控制台输出及 `changes`。

## 小批量写入

用预览中实际的人员 ID，逗号分隔，首批最多 3 人：

```bash
python3 scripts/emby_sync.py apply --ids 123,456
```

`123,456` 是格式示例，必须换成预览里的真实 ID。再次输入同一个主 Emby 地址和 Key。工具会核对服务器 ID、地址、人员类型、预览前后的字段与头像标记；不一致就停止。

写入前保存完整人员 DTO 到 `emby-backups`；更新中文名，将有来源的生日/三围/履历追加到简介，保留原有简介。生日原字段非空时保留，不强行覆盖。新写入的元数据字段加入 LockedFields，减少后续刮削覆盖。每人写入后重新读取验证。

只调用人员条目接口，不触碰影片、目录、NFO、影片 People 关系和 Emby 数据库。不保证不同客户端立即刷新缓存，也不把同名的多个 ID 当作已合并。头像写入与文字写入不是事务；若中途出错可能已部分成功，日志会保留备份路径，停止后先核对，不盲目重复 apply。首版提供备份，但尚无自动恢复命令。

## 如何验证

在主 Emby 找到对应影片 → 点演员头像 → 检查人员 ID 对应的名字、头像、简介及出演影片是否正常。若仍显示旧名字，先重新打开条目，核对是否打开了另一个重复人员 ID。

当前仅通过本地逻辑测试，尚未连接你的 NAS 实测。API 兼容性以你实际 Emby 版本为准。

官方接口文档：
- https://dev.emby.media/reference/RestAPI/PersonsService/getPersons.html
- https://dev.emby.media/reference/RestAPI/ImageService/postItemsByIdImagesByType.html
- https://dev.emby.media/reference/RestAPI/ItemUpdateService.html

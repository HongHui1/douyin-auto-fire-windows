# 抖音自动续火花 · Windows 增强版

基于 [unmev/douyin-auto-fire](https://github.com/unmev/douyin-auto-fire) 的非商业二次开发，面向 Windows 电脑本地定时运行。保留原项目的 Playwright 发送流程，并增加持久化登录、静默运行和本地分类文案。原项目作者为 **unmev**，本改版维护者为 **HongHui1**。

本仓库及发布压缩包只包含源码、示例配置和文档。你需要在自己的电脑上安装依赖、扫码登录和填写好友昵称。

## 主要功能

- 持久化浏览器目录：扫码登录与日常运行共用设备目录，登录过期时重新验证。
- Windows 任务计划程序：默认每天 21:00，支持自定义时间、错过后补跑和睡眠唤醒。
- 后台运行：日常任务使用隐藏窗口；首次扫码登录会打开浏览器。
- 70 条本地文案：文艺 30%、日常 35%、角色扮演 24%、虚构事件 10%、彩蛋 1%。无需 AI 接口或密钥。
- 同一好友同一天选文案固定，相邻日期不重复；生成失败时使用固定续火消息。
- 保留每日发送历史、发送结果检查、日志好友别名及多行消息适配。

当天发送状态不确定时保守跳过，避免重复。关机、退出 Windows 登录、断网、登录过期、平台验证或页面改版仍可能导致失败；不承诺每天必定续火成功。

## 快速开始

需要 **Windows 10/11、Python 3.11+、网络和本人抖音账号**。安装 Python 时建议包含 Python Launcher。将项目解压到你有写入权限的目录，在该目录打开 PowerShell。

### 1. 安装与初始化

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

这会创建 `.venv`、安装 Python 依赖及 Chromium，并在不存在时从示例创建 `.env`、`config.json`。已有配置不会覆盖。Python 不在 Launcher 中时，可指定可执行文件：

```powershell
.\setup.ps1 -PythonCommand "C:\Python313\python.exe"
```

### 2. 填写自己的好友

编辑 `config.json`，把 `请填写好友昵称` 替换为抖音私信中可搜索的准确昵称。先配置一个好友，消息保持 `streak` 即可使用分类文案：

```json
{
  "friends": ["好友A"],
  "messages": [{"type": "streak"}],
  "prevent_duplicates": true
}
```

需要固定消息时改为 `{"type": "text", "value": "🔥 今日续火打卡"}`。更多字段见 `config.example.json`。

### 3. 扫码登录

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\login.ps1
```

在弹出的浏览器里使用手机抖音扫码，并由本人完成平台要求的验证。默认状态保存在 `.browser-profile/`。仅当私信好友搜索框可用时脚本才确认成功；没有确认成功时请重新运行。

### 4. 演练后发送

```powershell
# 只验证登录与好友定位，不发送
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-daily.ps1 -DryRun

# 确认演练正常后，真实发送
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-daily.ps1
```

### 5. 开启每日定时任务

```powershell
# 默认每天 21:00，按电脑本地时钟执行
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-task.ps1

# 自定义时间
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-task.ps1 -Time "20:30"

# 查看任务
Get-ScheduledTaskInfo -TaskName "DouyinAutoFire-Windows-Daily"

# 移除本项目创建的任务
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-task.ps1 -Remove
```

此版本使用独立任务名，不会覆盖其他版本的任务。若旧版本也在使用同一账号，请先自行停用其中一个，避免重复运行。任务只在当前用户已登录 Windows 时执行；睡眠唤醒和补跑受系统、电源及网络设置影响。移动项目目录后须重新注册任务。

## 查看日志与文案

启动日志位于 `logs/`，程序日志和历史位于 `artifacts/`。成功标记用于避免同一天反复启动；不要随意删除发送历史或成功标记来试发。

```powershell
# 完全离线，不读取登录凭证，也不打开抖音
.\.venv\Scripts\python.exe .\scripts\preview_copy.py --days 7
.\.venv\Scripts\python.exe .\scripts\preview_copy.py --all
```

文案位于 `app/copywriting.py`。古诗、俳句和英文诗节选的作者、作品与核对来源见 [文艺类出处](docs/literary-sources.md)。外文保留原文，没有采用来源不明的现代译文。

## 开发与打包

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\release_guard.py --tracked
.\.venv\Scripts\python.exe .\scripts\build_release.py
```

打包使用 `release-files.txt` 的显式文件清单，并检查敏感文件名、访问令牌、私钥和本机用户路径。仅依靠 `.gitignore` 不能保证安全。发布前还须检查是否写入真实姓名、好友配置或自定义凭证，详见 [隐私说明](docs/privacy.md)。

## 来源与许可

本改版以原项目提交 [`af0035f`](https://github.com/unmev/douyin-auto-fire/commit/af0035f764d3a1adac5884bc3d73adcf031a3dd6) 为基础，保留原作者版权声明和 [PolyForm Noncommercial License 1.0.0](LICENSE)。源码以新的 Git 历史发布，原项目及本地改动来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [CHANGELOG.md](CHANGELOG.md)。

允许的非商业用途包括个人学习、修改和按许可证分享。不得把原代码或衍生版本改挂为可任意商用的许可；收费脚本、付费部署、收费服务等商业用途须另获授权。把副本分享给朋友时也应保留 `LICENSE` 及原作者必要声明。项目与抖音官方无隶属关系，使用时应遵守平台规则并尊重好友意愿。

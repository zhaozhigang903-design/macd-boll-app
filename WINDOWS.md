# MACD Windows 计算端

Windows版和云端版使用同一个 GitHub 代码库、同一套 EV 规则，不是两个独立系统。

## 一键启动

1. 安装 Python 3.11 或更新版本。
2. 下载/克隆本仓库。
3. 双击 `start_windows.bat`。
4. 浏览器打开 `http://127.0.0.1:8501`。

第一次启动会自动创建 `.venv` 并安装依赖，之后启动会更快。

## 与云端共享数据

核心数据共享依赖一个中央 PostgreSQL：

- 持仓
- 持仓快照
- Forward Test
- 研究任务和研究结果
- 策略优化实验
- 候选策略版本

行情K线、EV缓存和其他可重新计算的数据保留在每台机器本地，不上传中央数据库。

### Windows 配置

复制：

`windows_config.example.bat`

为：

`windows_config.bat`

然后填写同一个 PostgreSQL 的 **外部连接地址**：

`set SHARED_DATABASE_URL=postgresql://...`

该文件已加入 `.gitignore`，不要提交到 GitHub。

### 云端配置

在 Render 服务的环境变量中设置：

`SHARED_DATABASE_URL`

云端建议使用同一个 PostgreSQL 的内部/私有连接地址；Windows 使用同一数据库的外部 SSL 连接地址。

## 本地缓存位置

Windows 默认保存到：

`%LOCALAPPDATA%\MACD-BOLL\analysis_history.db`

其中行情缓存用于加速全市场扫描和长周期回测。即使本地缓存被删除，核心共享数据仍可从 PostgreSQL 恢复。

## 架构

```
Windows 计算端 ─┐
                ├─ 同一套代码 / 同一套策略规则
云端访问端 ─────┘
        │
        ├─ PostgreSQL：核心共享数据
        └─ 本地SQLite：行情与计算缓存
```


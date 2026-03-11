# 🚀 部署指南

## 第一步：创建 GitHub 仓库

1. 打开 https://github.com/new
2. 仓库名：`stock-dashboards`
3. 可见性：**私有** (Private) - 保护 API Key
4. 不要初始化 README/.gitignore
5. 点击 "Create repository"

## 第二步：推送代码

在终端执行：

```bash
cd /home/venger/projects/stock-dashboards

# 重命名分支为 main
git branch -M main

# 添加远程仓库 (替换为你的用户名)
git remote add origin https://github.com/SuperAvenger/stock-dashboards.git

# 推送代码
git push -u origin main
```

## 第三步：配置 GitHub Secrets

1. 进入仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 "New repository secret"
3. 添加以下 3 个 Secrets：

| Name | Value | 来源 |
|------|-------|------|
| `LONGPORT_APP_KEY` | `58ab63ae82794fe7bdcf4320718d6147` | `/home/venger/.openclaw/workspace/alibaba_monitor/config/longbridge.conf` |
| `LONGPORT_ACCESS_TOKEN` | `m_eyJhbGci...` (完整 Token) | 同上 |
| `FEISHU_WEBHOOK` | `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx` | 飞书机器人 |

## 第四步：启用 GitHub Actions

1. 进入仓库 → **Actions** 标签页
2. 点击 "I understand my workflows, go ahead and enable them"
3. 点击左侧 "Daily Stock Dashboards"
4. 点击 "Run workflow" 手动测试一次

## 第五步：启用 GitHub Pages

1. 进入仓库 → **Settings** → **Pages**
2. Source 选择 **GitHub Actions**
3. 等待第一次运行完成后，页面会自动发布

## 第六步：获取飞书 Webhook

1. 打开飞书 → 选择一个群或私聊机器人
2. 右上角 "..." → 添加机器人
3. 选择 "自定义机器人"
4. 复制 Webhook 地址（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx`）

## 测试运行

推送代码后，手动触发一次 Workflow：

```bash
# 或者在 GitHub UI 上点 "Run workflow"
```

等待 2-3 分钟，检查：
- ✅ Actions 页面显示绿色成功
- ✅ 飞书收到推送消息
- ✅ GitHub Pages 可访问看板

## 访问在线看板

- 🇭🇰 港股：`https://SuperAvenger.github.io/stock-dashboards/hk-dashboard.html`
- 🇺🇸 美股：`https://SuperAvenger.github.io/stock-dashboards/us-dashboard.html`

---

## ⚠️ Token 过期提醒

长桥 Access Token 有效期约 90 天，下次过期时间：**2026-04-01**

到期前需要：
1. 重新生成长桥 Token
2. 更新 GitHub Secrets 中的 `LONGPORT_ACCESS_TOKEN`
3. 重新运行 Workflow

建议：在日历中设置提醒，提前 7 天更新。

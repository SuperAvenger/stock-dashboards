# 📊 股票监控看板

每日自动生成港股/美股监控看板，推送到飞书 + 部署到 GitHub Pages。

## 功能

- ✅ 每天早上 7:00 自动更新
- ✅ 港股 + 美股双看板
- ✅ 飞书推送摘要
- ✅ GitHub Pages 托管 HTML 看板
- ✅ 量化评分系统（0-100 分）
- ✅ 因子解释与数据质量标记（模拟数据会明确降级置信度）

看板中的结论表示个人研究优先级，不是交易指令，也不会连接券商下单。

生产运行不会自动生成模拟行情或基本面。缺少长桥凭证或接口失败时，相关股票会被跳过或标记为数据不可用。仅演示时可显式设置 `ALLOW_SIMULATED_DATA=1` 生成模拟行情；模拟数据始终降低研究置信度。

## 配置

### 1. GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 添加：

| Secret Name | Value |
|------------|-------|
| `LONGPORT_APP_KEY` | 长桥 APP_KEY |
| `LONGPORT_APP_SECRET` | 长桥 APP_SECRET |
| `LONGPORT_ACCESS_TOKEN` | 长桥 Access Token |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook |

### 2. 股票池配置

编辑 `config/stocks.json` 添加/删除股票。

## 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export LONGPORT_APP_KEY="your_key"
export LONGPORT_APP_SECRET="your_secret"
export LONGPORT_ACCESS_TOKEN="your_token"
export FEISHU_WEBHOOK="your_webhook"

# 运行
python scripts/hk_dashboard.py
python scripts/us_dashboard.py
python scripts/push_to_feishu.py
```

## 手动触发

在 GitHub Actions 页面点击 "Run workflow" 手动运行。

## 输出

- `output/hk-dashboard.html` - 港股看板
- `output/us-dashboard.html` - 美股看板
- `output/hk-data.json` - 港股数据
- `output/us-data.json` - 美股数据

## 查看在线看板

- 🇭🇰 [港股看板](https://SuperAvenger.github.io/stock-dashboards/hk-dashboard.html)
- 🇺🇸 [美股看板](https://SuperAvenger.github.io/stock-dashboards/us-dashboard.html)

## License

MIT

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for reliability, research, and read-only MCP expansion priorities.

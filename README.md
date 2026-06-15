# 个人资产管理平台

按平台（富途/盈透等）+ 币种（人民币/美元）管理股票、基金、债券、加密等资产；
一级界面显示总资产、今日涨跌，支持实时汇率与 ¥/$ 币种切换，一键更新行情。

技术栈：**FastAPI + SQLite + akshare**（后端） / **React + Vite + Ant Design**（前端），前后端分离，便于以后上云和做手机端。

---

## 最简单：一键启动

> 首次使用前需先装好依赖（见下面「一、启动后端」「二、启动前端」里的安装步骤），之后日常启动只需双击脚本。

- **双击 `start.bat`** —— 自动拉起后端(8000)+前端(5173)，几秒后打开浏览器。会弹出两个窗口（后端/前端），用的时候保持开着。
- **双击 `stop.bat`** —— 一键停止前后端。

手机访问：连同一 Wi-Fi，打开前端窗口里显示的 `Network` 地址（如 `http://192.168.1.2:5173`）。

---

## 目录

```
FinancialSystem/
├─ backend/      FastAPI 后端（API + 行情/汇率 + SQLite）
└─ frontend/     React 前端（Dashboard / 平台管理 / 资产管理）
```

---

## 一、启动后端

```powershell
cd backend
# 首次：建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
# Windows + Microsoft Store 版 Python 若卡在 jsonpath 构建，先设这个环境变量：
$env:SETUPTOOLS_USE_DISTUTILS = "stdlib"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 启动（http://localhost:8000，交互式文档 /docs）
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

> Windows 提示：请用 PowerShell 直接调用 `.\.venv\Scripts\python.exe`，
> 不要在 Git Bash 里跑 Store 版 Python 的虚拟环境（可能 segfault）。

## 二、启动前端

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5173
```

前端已配置把 `/api` 代理到后端 `:8000`，并开启 `host`，
**同一局域网下手机浏览器**访问 `http://<电脑IP>:5173` 即可使用。

---

## 三、数据源说明

| 类型 | 数据源 | 说明 |
|---|---|---|
| A股/港股/美股/场内基金 | akshare（东方财富快照） | 免费、无需 key；延迟约 15 分钟 |
| 场外基金 | akshare 基金净值 | 按基金代码取最近单位净值 |
| 加密货币 | CoinGecko 免费接口 | symbol 支持 BTC/ETH 等或直接填 coingecko id |
| 汇率 USD/CNY | open.er-api.com（免费） | 失败回退中行牌价 |

行情为**手动刷新**（点「更新行情」），省调用、最可控。

---

## 四、后续迭代（架构已预留）

- 上云 + 手机访问：后端容器化部署，SQLite 换 PostgreSQL，前端构建为静态站/PWA
- 自动定时更新：后端加 APScheduler，复用现有刷新逻辑
- 多用户登录：加 JWT 鉴权
- 券商 API 直连：富途 OpenAPI / IBKR API 自动同步持仓
- 资产走势图：`snapshot` 表已每次刷新埋点，可直接画历史净值曲线

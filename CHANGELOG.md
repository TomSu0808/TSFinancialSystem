# 更新日志 (CHANGELOG)

> 记录每次迭代的改动。**最新的写在最上面。**
> 每条改动请按下面模板填写，方便日后回溯「为什么这么改」。

## 填写模板（复制下面这块）

```
## [版本/日期] - YYYY-MM-DD
### 类型：✨新增 / 🐛修复 / ♻️重构 / ⚡优化 / 📝文档 / 💥破坏性变更
- **改了什么**：一句话说明
- **为什么**：动机 / 解决的问题
- **影响范围**：涉及的文件或模块（如 backend/routers/holdings.py、前端 Dashboard）
- **注意事项**：是否需要重启、是否影响数据库结构、是否需要重装依赖
```

---

<!-- 在下面这条横线下方追加新记录，保持最新在最上 -->

## [UI] - 2026-06-29 登录页隐私修复与移动端布局优化

### 类型：🐛修复 / ⚡优化

- **改了什么**：
  - **移除登录页模拟持仓数据**：删除 `ProductPreview` 组件（含模拟总资产金额、资产配置比例、笔记条目），替换为 `FeatureHighlights`（四格功能亮点卡片），不再展示任何持仓相关数字。
  - **移动端布局优先**：登录/注册卡片在小屏（xs）通过 Ant Design Col `order` 属性提升至首位，功能介绍区排在下方；桌面端（md+）恢复左右并列布局。
  - **清理无用 import**：移除 `FundOutlined`、`SwapOutlined`、`ReadOutlined`、`RiseOutlined`、`SafetyOutlined` 等不再使用的图标引用。
- **为什么**：登录页展示模拟持仓数字会被误解为真实数据泄露，且移动端用户需要第一眼看到登录表单而非产品介绍。
- **影响范围**：`frontend/src/pages/Login.jsx`。
- **注意事项**：无破坏性变更，仅 UI 调整；`npm run build` 通过。

## [Phase 3 / v3.1-v3.3] - 2026-06-28

### ✨新增 — v3.1 定时自动刷新

- **AutomationRun 模型**：每次自动/手动全量刷新任务的执行日志（状态、用户数、行情更新数、快照数、错误信息）。
- **automation_service.py**：纯函数服务层，支持全量刷新（所有用户）和单用户刷新，解耦 HTTP 层，可被调度器和 API 共用。
- **scheduler.py**：asyncio 轻量调度器，FastAPI lifespan 启动/关闭；支持 `AUTO_REFRESH_TIME`、`AUTO_REFRESH_INTERVAL_HOURS`、`AUTO_REFRESH_TIMEZONE`、`AUTO_REFRESH_ON_STARTUP` 配置。
- **GET /api/automation/status**：返回配置和最近一次运行结果。
- **POST /api/automation/run-now**：手动触发单用户刷新，带进程内锁防并发。
- **GET /api/automation/runs**：最近 20 次任务记录。
- **Dashboard** 新增「自动刷新状态」卡片：显示启用状态、计划时间、最近运行结果；提供「立即运行」入口。

### ✨新增 — v3.2 站内提醒系统

- **AlertRule 模型**：提醒规则（price_above/below、day_change_pct、allocation_above/below、price_stale、refresh_failed），支持关联持仓或标的代码。
- **AlertEvent 模型**：触发的提醒事件，严重度分 info/warning/critical，状态 unread/read/dismissed。
- **alert_service.py**：评估逻辑，支持 8 种提醒类型，当天同规则去重，不重复刷屏。
- **routers/alerts.py**：规则 CRUD + 事件列表/标记/忽略/全部已读/手动评估，全部用户隔离。
- **Alerts.jsx**：新提醒页面，两 Tab（事件/规则），规则支持持仓下拉关联，事件支持标记已读/忽略。
- **导航**：顶部菜单新增「提醒」入口。
- **Dashboard** 未读提醒摘要卡片：展示最近 3 条未读，链接到提醒页面。

### ✨新增 — v3.3 PostgreSQL 可选支持

- `database.py` 新增 `_table_exists()` / `_column_exists()` 工具函数，兼容 SQLite（PRAGMA）和 PostgreSQL（information_schema）。
- `_migrate_add_user_id()` 不再只对 SQLite 运行，两种数据库均可执行列补充迁移。
- `requirements.txt` 新增 `psycopg2-binary>=2.9`（可选，仅 PG 部署时需要）。
- 新模型（AutomationRun、AlertRule、AlertEvent）由 `SQLModel.metadata.create_all` 自动建表，SQLite 和 PG 均适用。

### ✨新增 — 配置项

- `AUTO_REFRESH_ENABLED`、`AUTO_REFRESH_TIME`、`AUTO_REFRESH_INTERVAL_HOURS`、`AUTO_REFRESH_TIMEZONE`、`AUTO_REFRESH_ON_STARTUP`
- `ALERTS_ENABLED`

### 📝文档

- README.md / README.zh-CN.md 更新功能表、配置表、路线图、PostgreSQL 部署说明。

### 🐛修复

- alert_service.py 函数返回注解改用 `Optional[T]`，兼容 Python 3.9。

## [新增] - 2026-06-28 研究闭环：AI 报告跟踪 / 决策日志 / 持仓研究摘要

### 类型：✨新增

- **改了什么**：
  - **AI 报告结构化输出**：`research_prompt_builder.py` 在所有报告 prompt 的 Execution Requirements 区块追加「研究闭环输出要求」，要求 AI 必须输出六个固定章节——结论摘要、核心假设、主要风险、待验证问题、跟踪指标、行动项；行动项必须使用清单列表；报告必须标注数据时点；不确定信息必须标注假设或待验证；不得包装成确定性建议。中英文报告使用对应语言标题结构（英文为 Summary / Core Assumptions / Key Risks / Questions to Verify / Tracking Metrics / Action Items）。
  - **Note 模型升级为投资决策日志**：Note 新增字段 `related_holding_id`、`source_report_id`、`symbol`、`note_type`（thesis/risk/review/action/observation/general）、`status`（active/resolved/invalidated/archived）、`tags`（逗号分隔）；旧数据自动迁移，默认 note_type=general / status=active；`NoteCreate` / `NoteUpdate` 同步扩展；`_migrate_add_user_id` 补足 note 表新列。
  - **Notes API 升级**：`GET /api/notes` 支持按 symbol、note_type、status、related_holding_id、source_report_id、keyword（标题+内容模糊）筛选；create/update 新增字段；校验 related_holding_id / source_report_id 属于当前用户，不合法返回 404；用户隔离不变。
  - **AI 报告生成跟踪事项**：新增 `POST /api/research/reports/{report_id}/tracking-notes`；解析报告 Markdown 中的「行动项」或「Action Items」章节（支持 `#`、`##`、`###` 标题，支持 `-`/`*`/`+`/有序列表行）；每条行动项创建一条 note_type=action 的 Note，携带 source_report_id、related_holding_id、symbol（优先取 report.symbol，否则从 related holding 取）；重复调用返回已有记录（reused=true），不重复创建；无 report_md 或无行动项章节返回 400。
  - **持仓研究摘要**：新增 `GET /api/holdings/{holding_id}/research-brief`；按 related_holding_id 或 symbol 双向匹配返回当前用户的 notes（最多 20 条，按 updated_at 倒序）和 reports（最多 10 条）；严格用户隔离。
  - **Notes 页面改造**：Notes.jsx 重写为投资决策日志，新增筛选栏（关键词、symbol、类型、状态）、类型/状态 Tag 展示、tags 展示、来源报告标识；创建/编辑 Modal 增加 note_type、status、symbol、tags 字段；支持读取 URL query（?symbol=AAPL、?source_report_id=12、?note_type=action）并初始化筛选；保留自由文本笔记能力。
  - **Research 页面**：ReportDetail 在报告完成且有内容时展示「生成跟踪事项」按钮，点击调用 tracking-notes 接口，成功后提示生成数量并附「前往查看」链接（带 source_report_id 过滤跳转 /notes）；重复调用时提示「已存在跟踪事项」。
  - **PlatformDetail 持仓研究记录**：持仓表格操作列新增书本图标按钮，点击打开 Drawer，展示该持仓相关 notes（按类型分组：买入逻辑、行动项、风险点、复盘、观察、笔记）和 AI 报告列表；Drawer footer 提供「查看全部相关笔记」和「去投研工作台」快捷跳转。
  - **API 层**：`listNotes(params)` 支持筛选参数；新增 `generateTrackingNotes(reportId)`、`getHoldingResearchBrief(holdingId)`。
  - **测试**：新增 `backend/tests/test_notes_extended.py`（13 个测试，覆盖新字段 CRUD、五种筛选维度、用户隔离、related_holding 越权拒绝）和 `backend/tests/test_research_tracking.py`（12 个测试，覆盖中英文行动项提取、无 report_md/无行动项的 400、重复调用、symbol 来源逻辑、research brief 基础/symbol 匹配/用户隔离、prompt 六章节验证、清单列表要求）。全套 152 个测试通过。
- **为什么**：对应 `6_28_advice.md` 第二阶段：让 AI 报告结论沉淀为可跟踪的行动项，让笔记成为关联标的和持仓的投资决策日志，让持仓页能直接看到 thesis / 风险 / 复盘记录，形成「研究→报告→跟踪→复盘」完整闭环。
- **影响范围**：`backend/models.py`（Note 表+Schema）、`backend/database.py`（migration）、`backend/research_prompt_builder.py`、`backend/routers/notes.py`（重写）、`backend/routers/research.py`（新增接口）、`backend/routers/holdings.py`（新增接口）；新增 `backend/tests/test_notes_extended.py`、`backend/tests/test_research_tracking.py`；`frontend/src/api/index.js`、`frontend/src/pages/Notes.jsx`（重写）、`frontend/src/pages/Research.jsx`、`frontend/src/pages/PlatformDetail.jsx`。
- **注意事项**：
  - 无破坏性变更，Note 老数据 note_type=general / status=active，自动兼容。
  - `source_report_id` 外键指向 `researchreport` 表，仅逻辑关联，删除报告时 notes 的 source_report_id 不级联清空（SQLite 不强制 FK）。
  - Notes 页面 URL query 驱动筛选：从 Research 或 PlatformDetail 跳转时会自动带上对应参数。
  - 已验证：后端 pytest 152/152 通过，前端 `npm run build` 通过。

## [新增] - 2026-06-28 交易筛选 / Dashboard 归因 / CSV 导入

### 类型：✨新增

- **改了什么**：
  - **交易筛选**：`GET /api/transactions` 新增查询参数 `action`、`currency`、`keyword`（模糊匹配 name/symbol/note）、`date_from`、`date_to`；前端交易页筛选栏支持关键词输入、平台/类型/币种下拉、日期范围选择、查询 / 重置按钮，表格上方显示"共 N 条交易"；后端基于 SQLAlchemy `or_` 做模糊搜索，不在前端假筛选。
  - **Dashboard 归因**：`GET /api/summary` 新增三个字段——`top_movers`（今日涨跌贡献前 5，按 display_change 绝对值排序，仅含 open 持仓且有昨收/现价）、`return_breakdown`（未实现盈亏/已实现盈亏/分红利息/总收益，均按显示货币折算）、`data_freshness`（有价格持仓数、过期/缺失持仓数、stale_items 最多 5 条，仅统计 open 持仓，判定阈值 24 小时）；前端 Dashboard 插入"今日归因 / 数据状态"卡片，展示 Top movers（带涨跌额和涨跌%，颜色跟随 colorScheme）、收益组成 4 个数值、行情状态（过期持仓清单），兼容隐私打码。
  - **标准 CSV 导入**：新增 `POST /api/transactions/import/preview`（解析校验，不写库，返回逐行结果，最多展示前 100 行）和 `POST /api/transactions/import/commit`（全部有效则导入，有错误则返回 400 带 preview 结构，不导入任何一行）；CSV 字段：`date,action,name,symbol,platform,currency,quantity,price,fee,amount,note`；UTF-8-BOM 兼容；平台名必须精确匹配当前用户已有平台，buy/sell/dividend 同步 derived 持仓；前端交易页新增"导入 CSV"按钮，弹窗含格式说明、模板下载、Dragger 上传、逐行 preview 表格（错误行红色）、仅全部有效时可点确认导入。
  - **依赖**：后端新增 `python-multipart`（multipart/form-data 上传支持，已写入 requirements.txt）。
  - **测试**：新增 `backend/tests/test_transactions_filter_import.py`（18 个测试，覆盖筛选、CSV preview/commit、BOM、持仓同步）和 `backend/tests/test_summary_extended.py`（13 个测试，覆盖 top_movers 排序/截断/closed 排除、return_breakdown、data_freshness 时间阈值/截断/closed 排除）。全套 127 个测试通过。
- **为什么**：对应 `6_28_advice.md` 第一阶段：导入能力降低录入门槛，Dashboard 归因让用户知道"发生了什么"，交易筛选让流水账本从"记录"升级为"可查询的数据库"。
- **影响范围**：`backend/routers/transactions.py`、`backend/routers/summary.py`、`backend/requirements.txt`；新增 `backend/tests/test_transactions_filter_import.py`、`backend/tests/test_summary_extended.py`；`frontend/src/api/index.js`、`frontend/src/pages/Transactions.jsx`、`frontend/src/pages/Dashboard.jsx`。
- **注意事项**：
  - `python-multipart` 新增依赖：若手动管理虚拟环境，需 `pip install python-multipart`；`dev.py start` 会自动安装。
  - 无数据库结构变更，重启即生效。
  - CSV 导入仅支持标准模板格式，暂不兼容富途 / IBKR / 老虎等券商导出格式（列入后续路线图）。
  - 已验证：后端 pytest 127/127 通过，前端 `npm run build` 通过。

## [新增] - 2026-06-27 认证系统升级：邮箱验证、找回密码、旧 Token 失效与限流

### 类型：✨新增 / 💥破坏性变更（注册字段）

- **改了什么**：
  - **User 模型**：新增 `email_normalized`（唯一性用）、`email_verified`、`email_verified_at`、`password_changed_at`、`last_login_at`、`status`（active/disabled）字段；新增 `AuthToken` 表（统一存储邮箱验证和密码重置 token 的 sha256 哈希）。
  - **注册**：`email` 改为必填；username 加正则校验（3–32 位字母/数字/下划线/短横线）；密码最少 8 位；注册后自动发送邮箱验证邮件；`email_normalized` 唯一约束在应用层校验。
  - **新接口**：`POST /api/auth/resend-verification`（重发验证邮件，需登录，限流 3次/小时）；`POST /api/auth/verify-email`（验证邮箱 token）；`POST /api/auth/forgot-password`（防枚举，统一返回同样响应，限流 5次/小时）；`POST /api/auth/reset-password`（重置密码，token 有效期 30 分钟）。
  - **JWT 旧 token 失效**：`create_access_token` 加入 `iat`；`get_current_user` 检查 `iat < password_changed_at` 或 `status != active` 时返回 401，使 `change-password` 和 `reset-password` 后旧 JWT 立即作废。
  - **进程内限流**：新增 `rate_limit.py`，滑动窗口计数，不依赖 Redis；覆盖注册、登录、重发验证、忘记密码。
  - **邮件服务**：新增 `email_service.py`；`EMAIL_ENABLED=false`（默认）时打印验证链接到控制台方便本地开发，`true` 时通过 SMTP 发送；生产日志不打印 token 明文。
  - **生产配置检查**：`ENV=production` 时启动检查 `SECRET_KEY`/`APP_BASE_URL`/SMTP 配置完整性，缺失则 `sys.exit(1)`。
  - **前端**：注册表单 email 改必填、密码改 8 位下限；Login 页新增"忘记密码"表单（防枚举统一提示）和"重置密码"表单（从 URL `?token=` 读取）；App.jsx 已登录但邮箱未验证时显示不阻塞的顶部 Alert + "重新发送验证邮件"按钮；已登录时处理 `/verify-email?token=` 链接。
  - **测试**：新增 `backend/tests/test_auth.py`，覆盖 17 个场景（注册校验、邮箱验证、防枚举、token 失效、disabled 用户、限流核心）；全套 68 个测试通过。
- **为什么**：项目已公开开放注册，需要邮箱验证闭环防止垃圾账号；密码修改/重置后旧 JWT 立即失效是基本安全要求；找回密码是必要的用户体验；生产配置检查避免上线后忘记设 SECRET_KEY。
- **影响范围**：`backend/models.py`、`backend/auth.py`、`backend/routers/auth.py`、`backend/database.py`（迁移补列）、`backend/config.py`、新增 `backend/email_service.py`、新增 `backend/rate_limit.py`、`backend/main.py`、新增 `backend/tests/test_auth.py`、`backend/.env.example`；前端 `frontend/src/api/index.js`、`frontend/src/pages/Login.jsx`、`frontend/src/App.jsx`。
- **注意事项**：
  - **注册字段破坏性变更**：`email` 改为必填，现有前端客户端若依赖旧接口（email 为可选）需同步更新。
  - 老库无需手动迁移，`init_db()` 启动时自动给 `user` 表补 6 个新列（additive/幂等）；`AuthToken` 表自动建。
  - **本地开发验证邮箱**：`EMAIL_ENABLED=false` 时，注册后在终端看 `[DEV EMAIL]` 打印的链接，复制到浏览器即可。
  - **Fly.io 上线前**需 `fly secrets set ENV=production SECRET_KEY=<random> APP_BASE_URL=https://tsfinancialsystem.fly.dev`，如需真实邮件还需配置 `EMAIL_ENABLED=true SMTP_HOST=... SMTP_USERNAME=... SMTP_PASSWORD=...`。
  - 后端 `pytest` 68/68 通过；前端 `npm run build` 通过。

## [优化] - 2026-06-27 GitHub README、部署配置与资产驾驶舱布局
### 类型：📝文档 / ⚡优化 / 🐛修复
- **改了什么**：重写 GitHub README，新增英文主 README 与中文 `README.zh-CN.md`，顶部加入语言切换、线上站点 `https://tsfinancialsystem.fly.dev/`、项目截图、功能亮点、部署说明和路线图；补充 `backend/.env.example` 中的 AI provider 与汇率缓存配置；修正 DeepSeek 未配置时的错误提示，明确本地用 `backend/.env`、Fly.io 生产环境用 `fly secrets set`；汇率接口改为首次/过期自动刷新，避免长期显示默认 `7.2`；前端总览页重排为资产驾驶舱，新增现金占比、股票/ETF 占比、最大平台、累计收益率卡片，并将总资产走势提前；平台管理页改为“资产账户”页，新增账户卡片区和账户明细表；顶栏导航改为“总览 / 资产 / 交易 / 投研 / 笔记”。
- **为什么**：让 GitHub 首页更直观，访问者能立刻看到线上 Demo、截图、功能价值和中英文介绍；解决 Fly.io 上使用 DeepSeek 时环境变量未配置但错误提示误导的问题；让汇率展示更接近实时缓存逻辑；把产品布局从“后台管理表格”调整为更适合日常查看的个人资产驾驶舱。
- **影响范围**：`README.md`、`README.zh-CN.md`、`backend/.env.example`、`backend/research_service.py`、`backend/routers/fx.py`、`backend/tests/test_fx.py`、`frontend/src/App.jsx`、`frontend/src/pages/Dashboard.jsx`、`frontend/src/pages/Platforms.jsx`。
- **注意事项**：本地改动尚未推送 GitHub、也尚未部署到 Fly.io；线上生效需要先配置 `fly secrets set DEEPSEEK_API_KEY="..." AI_PROVIDER="deepseek"`，再执行 `fly deploy`。已验证：后端 `pytest` 通过，前端 `npm run build` 通过；Vite 仍有原有大 chunk 提示，不影响运行。

## [新增] - 2026-06-26 AI 投研工作台
### 类型：✨新增
- **改了什么**：新增投研工作台模块，接入 AI Berkshire 风格投研模板与本地 vendored skill 资源；支持生成单公司研究、投资委员会讨论、买入前检查、段永平提问、财报复盘、行业研究、组合复盘、新闻脉冲、投资 thesis 跟踪等报告；支持关联当前持仓、自动带入平台/币种/数量/成本/市值/盈亏等上下文；新增手动 prompt 生成、AI 直接生成、报告列表、报告详情、编辑、删除、刷新状态、取消任务、来源引用与免责声明；AI provider 抽象支持 GPT、DeepSeek、GLM、Claude，并保存 provider、model、prompt、skill_md、input_context、report_language、sources 等可复盘字段。
- **为什么**：把“资产记录”扩展到“投资研究闭环”，让持仓数据可以直接进入研究模板，减少复制粘贴和空白 prompt，形成从资产、交易、笔记到投研报告的工作流。
- **影响范围**：后端新增/更新 `ai_client.py`、`research_service.py`、`research_prompt_builder.py`、`research_templates.py`、`ai_berkshire_loader.py`、`routers/research.py`、`research_assets/ai_berkshire/`、`models.py`、`routers/backup.py`；前端新增/更新 `pages/Research.jsx`、`api/index.js`、`App.jsx`；测试覆盖 `backend/tests/test_research.py`。
- **注意事项**：使用 AI 直接生成报告需要在本地 `.env` 或生产环境 secrets 中配置对应 provider API key，例如 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`GLM_API_KEY`、`ANTHROPIC_API_KEY`；AI 生成内容仅用于投研记录，不构成投资建议。已通过 mock AI 的后端测试验证核心流程。

## [新增] - 2026-06-16 交易驱动持仓（前端 UX · Plan 2）
### 类型：✨新增
- **改了什么**：新建资产支持「按交易记录」（记一笔买入自动建 derived 持仓）/「直接手填」两种模式；derived 持仓数量/成本只读并标「流水」🔗、编辑禁用、不可直接删除；持仓表新增「已实现」列、清仓持仓默认隐藏（开关可显示并标「已清仓」）、卖超显示「数量异常」；总览顶部「累计盈亏」升级为「总收益」并悬浮拆分 未实现/已实现/分红；交易页文案改为说明会驱动持仓、保存后提示已同步；平台展开行标记 derived 持仓。
- **为什么**：把 Plan 1 的后端能力暴露给用户，让"交易→持仓"闭环可用。
- **影响范围**：前端 新增 `src/holdings.js`；`constants.js`、`pages/PlatformDetail.jsx`、`pages/Platforms.jsx`、`pages/Transactions.jsx`、`pages/Dashboard.jsx`。
- **注意事项**：无后端改动；无新依赖。前端无单测框架，验证为 `npm run build` + 浏览器手动冒烟。

## [新增] - 2026-06-15 交易驱动持仓（后端引擎）
### 类型：✨新增
- **改了什么**：derived(交易驱动)/manual(手填)混合持仓；买/卖流水自动驱动持仓数量与移动加权成本；卖出结转已实现盈亏；分红计入已实现收益；清仓持仓置 closed 并默认隐藏；总览新增 已实现盈亏/分红收入/总收益；备份导出导入往返保真且兼容旧备份。
- **为什么**：此前交易流水与持仓是两本账、需双重录入，且盈亏用单一成本价不准；让交易成为唯一事实来源，使数量与盈亏可信。
- **影响范围**：后端 `models.py`、`database.py`（迁移补列）、新增 `position.py`、`routers/transactions.py`、`routers/holdings.py`、`routers/summary.py`、`routers/backup.py`；新增 `backend/tests/`（pytest 测试基础设施 + 用例）。
- **注意事项**：重启后端自动迁移补列（additive、幂等），**存量手填持仓行为与数字不变**；derived 持仓数量/成本只读，需通过交易记录修改；**已知小限制**：经 API 直接修改某条已绑定 derived 持仓的交易的 symbol/platform 不会自动改绑到新持仓（前端将限制此操作，列为 Plan 2 / 后续跟进）；前端 UX 在 Plan 2 实现。

## [修复] - 2026-06-14 隐私模式漏打码
### 类型：🐛修复
- **改了什么**：隐私模式开启后仍显示金额的几处补齐打码：①总览「人民币/美元资产」原用 antd `<Statistic>` 不经过 fmt → 改为 fmt 渲染；②饼图悬浮提示的金额 `{c}` → 改函数格式化按隐私打码；③切换隐私时给内容区加 key 强制当前页重渲染，避免 antd 表格渲染优化导致偶发不刷新。
- **为什么**：`<Statistic>` 和 echarts tooltip 不走 fmt，绕过了打码逻辑。
- **影响范围**：前端 `Dashboard.jsx`、`App.jsx`
- **注意事项**：build 通过。

## [新增] - 2026-06-14 体验增强：隐私/深色/改密码/自动刷新
### 类型：✨新增
- **改了什么**：右上角用户菜单新增 4 项体验功能：
  1. **隐私模式**：一键把所有金额显示为 `****`（含走势图坐标轴），手机/公共场合/截图时用。状态本地记忆。
  2. **深色模式**：整站切换 antd 深色主题（含登录页）。状态本地记忆。
  3. **修改密码**：界面内改密码（校验原密码 + 两次确认），不用再走 CLI。
  4. **进总览自动刷新**：开启后每次进总览自动更新一次行情。状态本地记忆。
- **为什么**：提升日常使用体验，补齐「界面内改密码」的账号闭环。
- **影响范围**：
  - 后端：`routers/auth.py` 加 `POST /api/auth/change-password`；`models.py` 加 `PasswordChange`
  - 前端：`App.jsx`（4 个开关 + 改密码弹窗 + ConfigProvider 主题）、`constants.js`（隐私 fmt 打码 + isMasked）、`Dashboard.jsx`（自动刷新 + 图表打码）、`api/index.js`
- **注意事项**：
  - 隐私模式只影响「显示」，不改数据；靠 localStorage 记忆，换浏览器/清缓存会重置。
  - 已验证：前端 build 通过；改密码（原密码错→400、改成功→200、旧密码登录→401、新密码→200）。

## [新增] - 2026-06-14 五大功能批量上线
### 类型：✨新增
- **改了什么**：一次性补齐 5 个功能：
  1. **盈亏分析**：用已填的成本价算「累计盈亏」。总览顶部新增累计盈亏额+%，平台管理展开行、平台详情列表新增「成本/盈亏」列（红盈绿亏）。仅统计填了成本价的资产。
  2. **总资产走势图**：净值快照改为每人每天一条，总览新增折线图（默认近 180 天，¥/$ 跟随切换）。
  3. **资产配置占比**：总览新增「类型占比」饼图（股/基/债/加密/现金），与原「平台占比」并列。
  4. **数据备份导入/导出**：右上角用户菜单「导出备份」下载整账 JSON；「导入备份」覆盖式恢复（强确认 + 不可撤销提示）。
  5. **交易记录**：新增顶部菜单「交易记录」，独立流水账本（买入/卖出/分红/入金/出金/其它），可增删改，按平台筛选。**不自动改持仓**，仅作记录。
- **为什么**：把已采集但没用上的数据（成本价、净值快照）变现；补齐资产管理核心视图与数据安全。
- **影响范围**：
  - 后端：`models.py`（Snapshot 加 user_id/day；新增 Transaction 表 + schema；cost_basis/profit 助手）；`database.py`（snapshot 迁移补列）；`summary.py`（累计盈亏 + by_type + 每日快照 upsert）；新增 `routers/snapshots.py`/`transactions.py`/`backup.py`；`main.py` 挂载
  - 前端：`Dashboard.jsx`（盈亏/走势/类型饼图）、`PlatformDetail.jsx`+`Platforms.jsx`（盈亏列）、新增 `Transactions.jsx`、`App.jsx`（交易菜单 + 备份导入导出）、`api/index.js`、`constants.js`
- **注意事项**：
  - **重启后端**生效（`init_db()` 自动给 snapshot 补 user_id/day 列、建 transaction 表）。
  - 盈亏需要资产填了「成本价」且行情已刷新（无现价时市值记 0）。
  - 走势图需累计 ≥2 天数据；每天打开总览自动记一个点。
  - 「导入备份」是**覆盖式**：会清空当前账号全部数据再按备份重建，操作前先导出。
  - 已端到端验证：盈亏(1500/500/50%)、快照、交易 CRUD、备份导入导出往返均通过。

## [新增] - 2026-06-14 多用户登录（阶段1）
### 类型：✨新增
- **改了什么**：接入多用户登录系统。①打开应用先登录/注册（开放自助注册）；②数据按用户隔离——每人只能看到自己的平台/资产/心得；③登录用 JWT token，有效期 7 天；④密钥/CORS/注册开关全部走 `.env`，代码可安全开源；⑤忘记密码用 CLI 兜底：`python dev.py reset-password <用户名> [新密码]`、`python dev.py list-users`。
- **为什么**：为开源 + 上云 + 手机访问做准备；多人各自管理各自资产。
- **影响范围**：
  - 后端：新增 `config.py`/`auth.py`/`routers/auth.py`/`manage.py`；`models.py`（新增 User 表，platform/holding/note 加 user_id）；`database.py`（迁移：给旧表补 user_id 列）；`main.py`（挂 auth 路由 + CORS 走配置）；platforms/holdings/notes/summary/fx 全部加鉴权并按 user_id 过滤；requirements 加 `python-jose`/`bcrypt`/`python-dotenv`
  - 前端：新增 `pages/Login.jsx`；`api/index.js`（token 拦截器 + 认证接口）；`App.jsx`（登录守卫 + 顶栏用户名/登出）
  - 新增 `.env.example`，`.gitignore` 忽略 `.env`
- **注意事项**：
  - **重启后端**生效（`init_db()` 会自动建 user 表 + 给旧表补列，无需手动迁移）。
  - **第一个注册的账号**会自动认领你现有的全部数据（已验证：总额 ¥600,721.32 完整）。所以**首次请你自己先注册**，别让别人抢先。
  - 本地 `.env` 已生成（含随机 SECRET_KEY）；上云前务必在服务器设置固定 SECRET_KEY 并把 CORS_ORIGINS 收紧。
  - 阶段2（邮箱找回密码）、阶段3（HTTPS/上云部署）尚未做。

## [新增] - 2026-06-14
### 类型：✨新增
- **改了什么**：①平台管理页升级：每个平台可展开看下属资产（名称/现价/市值/仓位比例），新增「总额」列，支持 ¥/$ 切换；仓位比例只在本平台内计算，混合币种统一折算后再算占比。②顶部菜单新增「投资心得」，纯文本备忘录，可自由记录/编辑/删除投资语录与笔记。
- **为什么**：平台管理页原来只有平台名+备注，看不到各平台真实持仓与占比；另需一个地方沉淀投资心得。
- **影响范围**：
  - 前端：`pages/Platforms.jsx`（重写）、新增 `pages/Notes.jsx`、`App.jsx`（菜单+路由）、`api/index.js`（notes 接口）
  - 后端：`models.py`（新增 Note 表 + schema）、新增 `routers/notes.py`、`main.py`（挂载路由）
- **注意事项**：后端**新增了 `note` 表**——重启后端时 `init_db()` 会自动建表，无需手动迁移；不影响现有 platform/holding/data.db 数据。前端已 `vite build` 通过。

## [修复] - 2026-06-14
### 类型：🐛修复
- **改了什么**：重建后端虚拟环境 `backend/.venv`（坏的旧环境备份为 `backend/.venv_broken_mac`）
- **为什么**：旧 `.venv` 的 `pyvenv.cfg` 指向 macOS 路径（从 Mac 拷过来的），Windows 上无法启动 → 后端起不来 → 前端「加载汇总失败：status code 500」
- **影响范围**：仅 `backend/.venv`；数据库 `data.db`、业务代码均未改动，资产记录无损（总额 ¥600,721.32）
- **注意事项**：用系统 Python 3.11.9 重建并装好依赖；确认无误后可删除备份目录 `backend/.venv_broken_mac`

## [0.1.0] - 2026-06-14
### 类型：📝文档
- **改了什么**：新增 `CHANGELOG.md`（本文件）与 `ARCHITECTURE.md`（工程结构总览）
- **为什么**：记录每次迭代内容，并让后续开发能快速读懂整体框架
- **影响范围**：仅新增两个根目录文档，不影响代码与数据
- **注意事项**：无

## [0.1.0] - 起始版本
### 类型：✨新增
- **改了什么**：个人资产管理平台 MVP：平台管理、资产持仓管理、实时行情/汇率刷新、总资产与今日涨跌汇总、¥/$ 币种切换
- **为什么**：按平台 + 币种统一管理多类资产（股票/基金/债券/加密/现金）
- **影响范围**：backend（FastAPI + SQLite + akshare）、frontend（React + Vite + Ant Design）
- **注意事项**：首次运行需建后端虚拟环境并装依赖、前端 npm install（见 README）

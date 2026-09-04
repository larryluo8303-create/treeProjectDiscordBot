# BigTree — 客户端 App 与 Web 用户指南

> **版本：** 1.0.0
> **最后更新：** 2026-08-13

本指南覆盖 BigTree 客户端应用的搭建、使用与故障排查 — 包括**移动端 App**（`app-client/`）与 **Web 客户端**（`web-client/`）。它们是终端用户与 BigTree RAG Bot 交互的面向公众应用。

管理端 App 见 [`USER_GUIDE.md`](./USER_GUIDE.md)。  
技术设计文档见 [`CLIENT_DESIGN.md`](./CLIENT_DESIGN.md)。

---

## 目录

1. [前置条件](#1-前置条件)
2. [后端设置](#2-后端设置)
3. [移动端 App 设置](#3-移动端-app-设置)
4. [Web 客户端设置](#4-web-客户端设置)
5. [配置服务器连接](#5-配置服务器连接)
6. [聊天](#6-聊天)
7. [图片与图表分析](#7-图片与图表分析)
8. [书签](#8-书签)
9. [聊天历史](#9-聊天历史)
10. [每日摘要](#10-每日摘要)
11. [知识库搜索](#11-知识库搜索)
12. [活动与促销](#12-活动与促销)
13. [FAQ](#13-faq)
14. [课程归档](#14-课程归档)
15. [设置](#15-设置)
16. [部署到生产](#16-部署到生产)
17. [故障排查](#17-故障排查)

---

## 1. 前置条件

- **Node.js 18+** 与 **npm**
- BigTree Discord Bot 已以 `API_ENABLED=true` 运行（见 [后端设置](#2-后端设置)）
- 移动端：手机上的 **Expo Go**，或用于模拟器的 Xcode / Android Studio

---

## 2. 后端设置

客户端连接 Bot 的**公开 API** — 一组与 Bot 一同运行的未认证端点。

### 2.1 启用公开 API

确保 `.env` 中包含：

```env
API_ENABLED=true
API_PORT=8090
```

可选：添加 API Key 以限制访问：

```env
CLIENT_API_KEY=your-optional-api-key
CLIENT_RATE_LIMIT_PER_MINUTE=20
```

### 2.2 启动 Bot

```bash
python -m bot.main
```

验证 API 已运行：

```bash
curl http://localhost:8090/api/health
```

应看到：

```json
{
  "status": "ok",
  "uptime_seconds": 5.2,
  "timestamp": 1691234567.89
}
```

### 2.3 公开 API 端点

两个客户端消费的端点如下：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/public/chat` | POST | 发送问题并获取 RAG 回答 |
| `/api/public/analyze-image` | POST | 上传图表/图片供 GPT-4o 视觉分析 |
| `/api/public/faq` | GET | 获取缓存的 FAQ 项 |
| `/api/public/kb/search` | GET | 语义搜索（`?q=...&top_k=N`） |
| `/api/public/promos` | GET | 即将到来的促销 |
| `/api/public/lessons` | GET | 即将到来的课程 |
| `/api/public/lessons/archive` | GET | 已完成的历史课程 |
| `/api/public/digest` | GET | 近 24 小时活动摘要 |

无需登录。若设置了 `CLIENT_API_KEY`，通过 `x-api-key` HTTP 头传递。

---

## 3. 移动端 App 设置

移动端 App 位于 `app-client/` 目录。

### 3.1 安装依赖

```bash
cd app-client
npm install
```

### 3.2 用 Expo 启动

```bash
npx expo start
```

打开 Expo CLI，可选：

- 用手机上的 Expo Go **扫描二维码**（iOS/Android）
- 按 **`a`** 在 Android 模拟器打开
- 按 **`i`** 在 iOS 模拟器打开
- 按 **`w`** 在浏览器打开

### 3.3 App 导航

移动端使用**底部 Tab 栏**，共五个标签：

| Tab | 图标 | 内容 |
|---|---|---|
| **Chat** | 💬 | 主聊天界面，支持图片上传 |
| **Digest** | 📊 | 24 小时活动摘要 |
| **Search** | 🔍 | 知识库语义搜索 |
| **Events** | 📣 | 即将到来的促销与课程 |
| **More** | ⋯ | 其他功能菜单 |

**More** 标签可进入：

- **FAQ** — 常见问题
- **Bookmarks** — 已保存的 Bot 回答
- **History** — 过往聊天会话
- **Lesson Archive** — 已完成课程
- **Server Settings** — 配置服务器 URL 与 API Key
- **Push Notifications** — 开/关（需设备权限）

---

## 4. Web 客户端设置

Web 客户端位于 `web-client/` 目录。

### 4.1 安装依赖

```bash
cd web-client
npm install
```

### 4.2 启动开发服务器

```bash
npm run dev
```

App 打开于 **http://localhost:5173**。

### 4.3 Web 导航

Web 客户端使用**左侧边栏**，直达全部 9 个页面：

| 侧边栏项 | 路由 | 内容 |
|---|---|---|
| **Chat** | `/chat` | 主聊天界面，支持图片上传 |
| **Digest** | `/digest` | 24 小时活动摘要 |
| **Search** | `/search` | 知识库语义搜索 |
| **Events** | `/events` | 即将到来的促销与课程 |
| **FAQ** | `/faq` | 常见问题 |
| **Bookmarks** | `/bookmarks` | 已保存的 Bot 回答 |
| **History** | `/history` | 过往聊天会话 |
| **Lessons** | `/lessons` | 已完成课程归档 |
| **Settings** | `/settings` | 服务器 URL 与 API Key 配置 |

窄屏仅显示**图标**；宽屏（≥ 1024px）显示**图标 + 标签**。

---

## 5. 配置服务器连接

使用前需将 App 指向你的 BigTree Bot 服务器。

### 移动端 App

1. 打开 **More** 标签
2. 滚到 **Server Settings**
3. 输入 **Server URL**（例如 `http://192.168.1.100:8090`）
4. 若服务器需要，输入 **API Key**
5. 点击 **Save**

### Web 客户端

1. 在侧边栏点击 **Settings**
2. 输入 **Server URL**（例如 `http://localhost:8090`）
3. 若服务器需要，输入 **API Key**
4. 点击 **Save Settings**

> **重要：** 真机使用移动端时，请用电脑的**局域网 IP**（不要用 `localhost`）。确保网络可访问 8090 端口。

设置保存在本地，重启 App 后仍有效。

---

## 6. 聊天

Chat 页是与 BigTree 交互的主界面。

### 提问

1. 在底部输入框输入问题
2. 按 **Enter** 或点击 **Send**
3. BigTree 会回复，包含：
   - **置信度分数**（1–10）— 绿/黄/红着色
   - **来源引用** — 生成回答所用的知识库片段

### 对话上下文

聊天维护最近 10 条消息的滚动窗口作为上下文。因此 BigTree 能理解「能再解释一下吗？」或「那 ES 呢？」这类追问。

### 建议 Chips

聊天为空时会显示快速开始建议：

- **ES今天怎么看？** — 询问今日 ES 看法
- **什么是中枢？** — 询问交易概念
- **如何判断趋势？** — 询问趋势分析
- **Upload a chart** — 从上传图片开始

点击任一 chip 会填入输入框。

### 会话自动保存

每次对话自动保存到设备。过往对话可在 **History** 页找到。最多保留 **50** 个会话（最旧的自动删除）。

---

## 7. 图片与图表分析

两个 App 均支持上传图片（图表、截图、示意图），由 GPT-4o 视觉进行分析。

### 如何上传

**移动端 App：**
1. 点击输入框旁的**相机图标**
2. 选择拍照或从相册选取
3. 可选附带文字问题
4. 图片发送给 BigTree 分析

**Web 客户端：**
1. 点击输入框旁的**相机图标**
2. 从电脑选择图片文件
3. 可选附带文字问题
4. 图片发送给 BigTree 分析

### 支持格式

- JPEG、PNG、GIF、WebP
- 最大文件大小：**10 MB**

### BigTree 可分析的内容

- **股票图表** — 识别形态、支撑/阻力、趋势
- **技术指标** — 解读 MACD、RSI、均线等
- **截图** — 提取并解释截图中的文字或数据

上传的图片会在聊天中以内联预览显示。

---

## 8. 书签

保存重要的 Bot 回答，方便日后快速查阅。

### 保存书签

在聊天中，点击任意 Bot 消息上的**书签图标**（🔖）。问答对本地保存，包含：

- 原问题
- Bot 回答
- 置信度分数
- 保存日期

### 查看书签

**移动端：** More → Bookmarks  
**Web：** 侧边栏点击 **Bookmarks**

### 删除书签

每条书签有**垃圾桶图标** — 点击移除。删除前会要求确认。

### 存储上限

最多 **100** 条书签。超出后保存新书签时会自动删除最旧的。

---

## 9. 聊天历史

查看与管理过往对话。

### 查看历史

**移动端：** More → History  
**Web：** 侧边栏点击 **History**

会话按日期分组，显示：

- **会话标题**（首条消息，截断）
- **消息数量**
- **最近活动时间**

### 删除会话

每个会话有**删除按钮** — 点击移除，删除前会确认。

### 存储上限

最多 **50** 个会话。达到上限后自动删除最旧的。

---

## 10. 每日摘要

Digest 页展示 BigTree 近 24 小时活动摘要。

### 统计卡片

顶部三张卡片显示：

| 卡片 | 说明 |
|---|---|
| **Queries** | 近 24 小时收到的问题总数 |
| **Auto Replies** | 自动回答的问题数（高于置信度阈值） |
| **Avg Confidence** | 近期回答的平均置信度 |

### 热门问题

卡片下方为近 24 小时最常问问题的排序列表。

### 空状态

若无活动，显示 "No activity in the last 24 hours"。

数据每 **5 分钟**自动刷新。

---

## 11. 知识库搜索

用自然语言搜索 BigTree 知识库。

### 如何搜索

1. 进入 **Search** 页
2. 在搜索框输入查询（例如「中枢」或 "trend reversal"）
3. 按 **Enter** 或点击 **Search**

### 理解结果

每条结果显示：

- **Type badge** — 文档类型（`qa_pair`、`owner_message`、`youtube` 等）
- **Relevance score** — 与查询匹配程度的百分比
- **Text content** — 匹配的知识库条目

结果使用**语义搜索**（非关键词匹配）— 因此 "how to identify a trend" 也能匹配关于「趋势判断」的文档，即使没有完全相同的词。

---

## 12. 活动与促销

Events 页展示即将到来的活动。

### 促销区

显示即将到来的促销，包含：

- **标题**与**描述**
- **开始日期**
- **详情链接**（新标签页打开）

### 课程区

显示即将到来的课程，包含：

- **标题**与**内容描述**
- **排程日期**
- **重复徽章**（若课程会重复）

### 空状态

若无进行中的促销或即将到来的课程，对应区域显示 "No active promotions" 或 "No upcoming lessons"。

---

## 13. FAQ

查看由 BigTree 整理的常见问题。

**移动端：** More → FAQ  
**Web：** 侧边栏点击 **FAQ**

### 工作方式

FAQ 项以**可展开手风琴**展示。点击问题展开答案，再点一次折叠。

FAQ 由 GPT 根据常见高置信度查询自动生成，并缓存在服务器上（由 Bot 所有者在管理端刷新）。

---

## 14. 课程归档

浏览已完成的历史课程。

**移动端：** More → Lessons  
**Web：** 侧边栏点击 **Lessons**

每条归档课程显示：

- **标题**
- **内容/描述**
- **原排程日期**

按时间倒序（最新在前）。

---

## 15. 设置

配置 App 如何连接 BigTree 服务器。

### Server URL

BigTree Bot API 服务器的完整 URL（含端口）。例如：

- `http://localhost:8090`（本地开发）
- `http://192.168.1.100:8090`（手机局域网访问）
- `https://bigtree.example.com`（经反向代理的生产环境）

### API Key

若服务器配置了 `CLIENT_API_KEY`，在此填入匹配的 key。不需要 key 则留空。

### 保存

点击 **Save** 应用更改。对后续所有 API 调用立即生效。设置存于本地，重启后仍保留。

---

## 16. 部署到生产

### 16.1 移动端 App — Expo Build

使用 Expo Application Services 构建独立应用二进制：

```bash
cd app-client

# Android (.apk or .aab)
npx eas build --platform android

# iOS (.ipa) — requires Apple Developer account
npx eas build --platform ios
```

需要 [EAS 账号](https://expo.dev/eas)。详细说明见 [Expo build 文档](https://docs.expo.dev/build/introduction/)。

### 16.2 Web 客户端 — 静态构建

构建生产用 Web 客户端：

```bash
cd web-client
npm run build
```

在 `web-client/dist/` 生成优化后的静态文件（约 95 KB gzipped）。可部署到任意静态托管：

- **Nginx** — 将 `dist/` 复制到网站根目录
- **Vercel** — 在 `web-client/` 目录执行 `npx vercel --prod`
- **Netlify** — 拖放 `dist/`，或连接 Git 仓库
- **Cloudflare Pages** — 连接 Git，构建命令 `npm run build`，输出目录 `dist`

#### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name bigtree.example.com;
    root /var/www/bigtree-web/dist;
    index index.html;

    # SPA fallback — all routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 16.3 后端 CORS

后端已预配置 `allow_origins=["*"]`，任意 Web 客户端域名开箱即用。若生产环境要限制来源，编辑 `bot/api/server.py` 中的 CORS 中间件：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bigtree.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 17. 故障排查

### 无法连接服务器

- 确认 Bot 以 `API_ENABLED=true` 运行
- 检查设置中的 Server URL 是否匹配 Bot 地址与端口
- 测试连通性：`curl http://<host>:8090/api/health`
- 移动端使用电脑的**局域网 IP**（不要用 `localhost`）
- 确保 8090 端口未被防火墙拦截

### 聊天返回错误

- 查看 Bot 控制台错误信息
- 确认 Bot 的 OpenAI API Key 有效且有额度
- 确认 ChromaDB 已有数据（先运行 ingestion）

### 图片上传失败

- 确认图片为 JPEG、PNG、GIF 或 WebP
- 文件须小于 **10 MB**
- Bot 须在运行，且具备 GPT-4o 视觉所需的有效 OpenAI API Key
- 查看浏览器控制台（Web）或 Metro 日志（移动端）的具体错误

### 「Rate limited」提示

- 服务器按 IP 限制为 `CLIENT_RATE_LIMIT_PER_MINUTE`（默认：20）
- 稍等再试
- 如需可请 Bot 所有者提高速率限制

### 数据未加载（Digest、Events、FAQ 等）

- 确认设置中的服务器连接正确
- Bot 必须在运行 — 这些端点从 Bot 进程取实时数据
- 移动端下拉刷新，或 Web 重新加载页面

### 书签 / 历史消失

- 数据存在**设备本地**（不在服务器）
- 清除浏览器数据（Web）或 App 数据（移动端）会删除已存项
- 不同浏览器/设备各自独立存储

### Web 客户端空白页

- 在 `web-client/` 运行 `npm install`
- 查看浏览器控制台的 JavaScript 错误
- 确认访问正确 URL（开发环境为 `http://localhost:5173`）

### 移动端 App 无法启动

- 在 `app-client/` 运行 `npm install`
- 确认手机已安装 Expo Go
- 确认手机与电脑在同一网络
- 尝试 `npx expo start --clear` 重置 bundler 缓存

### IDE 中的 TypeScript / lint 错误

- 仅为编辑器警告 — 不影响运行中的 App
- 运行 `npm install` 可解决缺少模块的错误
- 打包器（Vite / Expo）负责编译，真实错误会显示在终端

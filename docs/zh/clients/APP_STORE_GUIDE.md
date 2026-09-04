# BigTree Chat App — App Store 发布指南

本指南介绍如何将 BigTree Chat 手机 App 发布到 Apple App Store 和 Google Play Store，让客户可以直接下载使用。

---

## 架构概览

```
客户手机 (BigTree Chat App)
        │
        ▼  HTTPS
你的服务器 (Bot + API Server, port 8090)
        │
        ├── /api/public/chat    ← App 发聊天请求
        ├── /api/public/faq     ← 获取 FAQ
        ├── /api/public/kb/search ← 知识库搜索
        └── /api/public/...     ← 其他公开 API
```

App 是一个独立的手机客户端，通过 HTTPS 调用你服务器上的 API。Bot 在服务器后台运行，同时服务 Discord 和手机 App。

---

## 前置条件

| 项目 | 说明 |
|------|------|
| **Apple Developer Account** | $99/年，https://developer.apple.com/programs/ |
| **Google Play Console** | $25 一次性费用，https://play.google.com/console/ |
| **Expo 账号** | 免费，https://expo.dev/signup |
| **EAS CLI** | `npm install -g eas-cli` |
| **Node.js** | >= 18 |
| **服务器** | 有公网 IP 的 VPS，已部署 Bot + API（见下方） |

---

## 第一步：部署后端服务器

App 需要一个可从公网访问的 API 服务器。

### 1.1 部署到 VPS

```bash
# 在服务器上
git clone <your-repo> && cd treeProjectDiscordBot
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 配置 .env（重要安全项）
cp .env.example .env
# 编辑以下关键配置：
#   DISCORD_BOT_TOKEN=<你的 Bot Token>
#   OPENAI_API_KEY=<你的 OpenAI Key>
#   OWNER_USER_ID=<你的 Discord ID>
#   API_SECRET_KEY=<随机32字符强密码>
#   CLIENT_API_KEY=<给客户端用的 API Key>

# 启动
nohup .venv/bin/python -m bot.main &
```

### 1.2 配置 HTTPS（必须）

App Store 要求所有网络请求使用 HTTPS。用 Nginx + Let's Encrypt：

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

Nginx 配置：

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

验证：`curl https://api.yourdomain.com/api/health` 应返回 `{"status": "ok", ...}`

---

## 第二步：配置 App 默认服务器地址

编辑 `app-client/src/api/client.ts`，将默认 URL 改为你的生产服务器：

```typescript
let _baseURL = 'https://api.yourdomain.com';  // ← 改为你的域名
```

这样客户下载后打开 App 就能直接使用，不需要手动配置。

---

## 第三步：准备 App 资源

### 3.1 App 图标

替换 `app-client/assets/` 下的文件：

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `icon.png` | 1024x1024 | App Store / 主图标 |
| `adaptive-icon.png` | 1024x1024 | Android 自适应图标前景 |
| `splash.png` | 1284x2778 | 启动画面 |
| `favicon.png` | 48x48 | Web 图标 |

可以用提供的脚本生成占位图（开发用）：

```bash
cd app-client
node scripts/generate-icons.js
# 然后将 SVG 转换为 PNG
```

**正式发布前，请使用专业设计的品牌图标。**

### 3.2 更新 app.json

编辑 `app-client/app.json`：

```json
{
  "expo": {
    "name": "BigTree Chat",           // App Store 显示名称
    "version": "1.0.0",               // 版本号
    "ios": {
      "bundleIdentifier": "com.yourcompany.bigtree"  // 你的 Bundle ID
    },
    "android": {
      "package": "com.yourcompany.bigtree"           // 你的 Package Name
    }
  }
}
```

---

## 第四步：EAS Build 构建

### 4.1 初始化 EAS

```bash
cd app-client
npm install -g eas-cli
eas login                    # 登录 Expo 账号
eas init                     # 关联项目（会自动填 projectId）
```

### 4.2 构建 iOS（提交 App Store）

```bash
# 预览版（内部测试）
eas build --platform ios --profile preview

# 正式版（提交 App Store）
eas build --platform ios --profile production
```

首次构建时 EAS 会提示你：
- 创建 iOS Distribution Certificate
- 创建 Provisioning Profile
- 这些都可以选择让 EAS 自动处理

### 4.3 构建 Android（提交 Google Play）

```bash
# 正式版
eas build --platform android --profile production
```

---

## 第五步：提交到商店

### 5.1 提交到 Apple App Store

```bash
# 直接从 EAS 提交到 App Store Connect
eas submit --platform ios --profile production
```

或者手动：
1. 从 EAS Dashboard 下载 `.ipa` 文件
2. 打开 Transporter (macOS) → 上传 `.ipa`
3. 登录 App Store Connect → 创建 App → 填写信息 → 提交审核

**App Store 审核要点：**
- 必须使用 HTTPS
- 需要隐私政策 URL
- 需要截图（iPhone 6.7"、5.5"、iPad）
- 描述清楚 App 功能

### 5.2 提交到 Google Play

```bash
eas submit --platform android --profile production
```

或者手动：
1. 从 EAS Dashboard 下载 `.aab` 文件
2. 登录 Google Play Console → 创建应用 → 上传 `.aab`
3. 填写商店信息 → 提交审核

---

## 第六步：客户使用流程

客户操作只需 3 步：

1. **下载 App** → App Store / Google Play 搜索 "BigTree Chat"
2. **打开 App** → 自动连接到你的服务器
3. **开始提问** → RAG Bot 自动回答

如果你设了 `CLIENT_API_KEY`，客户首次使用需要：
- 打开 App → More → Server Settings → 输入你提供的 API Key → Save

---

## App 功能一览

| Tab | 功能 |
|-----|------|
| **Chat** | 聊天界面，提问 → RAG Bot 自动回答，支持上传图片分析 |
| **Digest** | 每日活动摘要（查询数、自动回复率、热门问题） |
| **Search** | 搜索知识库历史内容 |
| **Events** | 查看即将到来的推广活动和教学课程 |
| **More** | FAQ、书签、聊天历史、教学归档、服务器设置 |

---

## 更新 App 版本

```bash
# 1. 修改代码
# 2. 更新 app.json 中的 version
# 3. 重新构建
eas build --platform all --profile production

# 4. 重新提交
eas submit --platform all --profile production
```

EAS 会自动递增 `buildNumber` (iOS) 和 `versionCode` (Android)。

---

## OTA 热更新（无需重新提审）

对于不涉及原生代码的 JS 更新，可以用 EAS Update 直接推送：

```bash
# 发布 OTA 更新（用户打开 App 自动更新，无需去商店重新下载）
eas update --branch production --message "修复XX问题"
```

这是 Expo 的一大优势——大部分更新不需要等 Apple 审核。

---

## 常见问题

### Q: 需要 Mac 才能发布 iOS 吗？
**不需要。** EAS Build 在 Expo 云端构建，Windows 也可以。只有本地调试模拟器时需要 Mac。

### Q: 构建要花钱吗？
EAS 免费计划每月 30 次构建，够用。付费计划可以更快排队。

### Q: 审核要多久？
- Apple：通常 1-3 个工作日
- Google：通常几小时到 1 天

### Q: 可以先内部测试吗？
可以。用 `preview` profile 构建，通过 TestFlight (iOS) 或 内部测试轨道 (Android) 分发给测试用户。

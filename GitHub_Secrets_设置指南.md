# GitHub Secrets 设置详细指南

## 🎯 目标
将敏感的邮件配置信息（密码等）安全地存储在GitHub Secrets中，让GitHub Actions可以读取但不会被公开。

---

## 📋 需要设置的Secrets列表

| Secret名称 | 值 | 说明 |
|-----------|-----|------|
| `EMAIL_SMTP_HOST` | `smtp.126.com` | 126邮箱SMTP服务器 |
| `EMAIL_SMTP_PORT` | `465` | SMTP端口（SSL） |
| `EMAIL_SENDER` | `clhy0806@126.com` | 发件人邮箱 |
| `EMAIL_PASSWORD` | `[您的邮箱密码]` | 邮箱密码（见下方说明） |
| `EMAIL_RECIPIENTS` | `clhy0806@126.com` | 收件人邮箱 |

---

## 🔑 关于邮箱密码的重要说明

### 如果是126邮箱，需要使用**授权码**，不是登录密码

#### 如何获取126邮箱授权码：

1. 登录126邮箱网页版：https://mail.126.com
2. 点击顶部「**设置**」→「**POP3/SMTP/IMAP**」
3. 开启「**IMAP/SMTP服务**」或「**POP3/SMTP服务**」
4. 点击「**生成授权码**」
5. 通过手机验证后，会显示一个16位的授权码（如：`abcd efgh ijkl mnop`）
6. **这个授权码就是 `EMAIL_PASSWORD` 的值**（去掉空格）

---

## 📝 详细步骤（带截图说明）

### 第1步：打开GitHub仓库

1. 在浏览器中访问：https://github.com/caiclhy0806/fx-tracker
2. 确认您已登录GitHub账号

---

### 第2步：进入Settings页面

在仓库页面，点击顶部导航栏的「**Settings**」选项卡

```
仓库页面布局：
┌─────────────────────────────────────────────────┐
│  Code  Issues  Pull requests  Actions  Projects  │
│  Security  Insights  ⚙️ Settings               │
└─────────────────────────────────────────────────┘
                          ↑
                    点击这里
```

---

### 第3步：找到Secrets and variables

在左侧菜单中：
1. 找到「**Security**」部分
2. 展开它
3. 点击「**Secrets and variables**」→「**Actions**」

```
左侧菜单：
┌──────────────────┐
│  Settings        │
│  ├─ General      │
│  ├─ Security     │
│  │   ├─ Secrets  │
│  │   │   and     │
│  │   │  variables│  ← 点击这里
│  │   │    → Actions│
│  ├─ ...          │
└──────────────────┘
```

---

### 第4步：添加第一个Secret

1. 点击页面右上角的「**New repository secret**」按钮

```
页面布局：
┌──────────────────────────────────────┐
│  Actions secrets                  │
│  ───────────────────────────────── │
│  [📋 Repository secrets]          │
│                                    │
│  Name          Value               │
│  (暂无)                           │
│                                    │
│     [+ New repository secret]     │
│           ↑                        │
│         点击这里                    │
└──────────────────────────────────────┘
```

2. 会弹出一个表单：

```
┌──────────────────────────────────────┐
│  Add a new secret                   │
│  ───────────────────────────────── │
│                                      │
│  Name                               │
│  ┌────────────────────────────────┐│
│  │ EMAIL_SMTP_HOST                ││
│  └────────────────────────────────┘│
│                                      │
│  Secret                             │
│  ┌────────────────────────────────┐│
│  │ smtp.126.com                   ││
│  │                                ││
│  └────────────────────────────────┘│
│                                      │
│  [  Cancel  ]    [  Add secret  ]  │
└──────────────────────────────────────┘
```

3. 填写：
   - **Name**: `EMAIL_SMTP_HOST`
   - **Secret**: `smtp.126.com`

4. 点击「**Add secret**」按钮

---

### 第5步：重复添加其他Secrets

按照同样的步骤，继续添加：

#### Secret #2
```
Name: EMAIL_SMTP_PORT
Secret: 465
```

#### Secret #3
```
Name: EMAIL_SENDER
Secret: clhy0806@126.com
```

#### Secret #4（重要！）
```
Name: EMAIL_PASSWORD
Secret: [您的126邮箱授权码，不是登录密码]
```
⚠️ 注意：如果还没有授权码，先按下方说明获取

#### Secret #5
```
Name: EMAIL_RECIPIENTS
Secret: clhy0806@126.com
```

---

### 第6步：验证所有Secrets已添加

添加完成后，页面应该显示：

```
┌──────────────────────────────────────┐
│  Actions secrets                  │
│  ───────────────────────────────── │
│  [📋 Repository secrets]          │
│                                    │
│  Name                Updated        │
│  ├─ EMAIL_PASSWORD   2 minutes ago  │
│  ├─ EMAIL_RECIPIENTS 2 minutes ago  │
│  ├─ EMAIL_SENDER     2 minutes ago  │
│  ├─ EMAIL_SMTP_HOST  2 minutes ago  │
│  └─ EMAIL_SMTP_PORT  2 minutes ago  │
│                                    │
│     [+ New repository secret]     │
└──────────────────────────────────────┘
```

---

## 🧪 测试GitHub Actions

设置完Secrets后，立即测试：

### 方法1：手动触发（推荐）

1. 进入仓库的Actions页面：
   https://github.com/caiclhy0806/fx-tracker/actions

2. 在左侧找到「**汇率数据每日抓取**」工作流

3. 点击工作流名称

4. 点击「**Run workflow**」按钮（右侧）

5. 在弹出的确认框中，点击绿色的「**Run workflow**」按钮

6. 等待运行完成（约2-3分钟）

7. 查看运行日志：
   - 绿色✅ = 成功
   - 红色❌ = 失败（点击查看错误日志）

---

## 📧 获取126邮箱授权码的详细步骤

如果还没有授权码，按以下步骤获取：

### 1. 登录126邮箱
访问 https://mail.126.com 并登录

### 2. 进入设置
点击顶部「**设置**」→「**POP3/SMTP/IMAP**」

### 3. 开启SMTP服务
找到「**POP3/SMTP/IMAP**」部分
- 如果「**IMAP/SMTP服务**」是关闭的，点击「开启」
- 如果已经开启，跳过此步

### 4. 生成授权码
- 点击「**生成授权码**」按钮
- 会要求验证：发送短信到指定号码
- 发送后会显示**16位授权码**

示例授权码格式：
```
abcd efgh ijkl mnop
```

### 5. 记录授权码
- **去掉空格**，变成：`abcdefghijklnmop`
- 这就是 `EMAIL_PASSWORD` 的值

---

## ⚠️ 常见问题

### Q1: 添加Secret时看不到值？
**A**: 正常！GitHub不会显示已保存的Secret值，只能看到名称和更新时间。

### Q2: 如何修改已添加的Secret？
**A**: 点击Secret名称旁边的「**Update**」按钮，重新输入值。

### Q3: GitHub Actions运行失败？
**A**: 检查：
1. 所有5个Secrets都已添加
2. `EMAIL_PASSWORD` 是授权码（不是登录密码）
3. 126邮箱的SMTP服务已开启

### Q4: 如何查看运行日志？
**A**: 
1. 进入 https://github.com/caiclhy0806/fx-tracker/actions
2. 点击最近一次运行
3. 点击「**fetch-and-update**」任务
4. 查看详细日志

---

## 🎉 完成标志

当您看到这个页面时，说明配置成功：

```
┌──────────────────────────────────────┐
│  ✅ 汇率数据每日抓取               │
│  ───────────────────────────────── │
│  所有步骤已完成                     │
│                                    │
│  ✓ 检出代码                        │
│  ✓ 设置Python环境                  │
│  ✓ 安装依赖                        │
│  ✓ 生成配置文件                    │
│  ✓ 运行汇率抓取脚本                │
│  ✓ 提交并推送更新                  │
└──────────────────────────────────────┘
```

---

## 📞 需要帮助？

如果在设置过程中遇到问题，请：
1. 截图错误信息
2. 告诉我具体在哪一步卡住
3. 我会提供针对性的解决方案

---

## 🔗 快速链接

- **仓库主页**: https://github.com/caiclhy0806/fx-tracker
- **Settings**: https://github.com/caiclhy0806/fx-tracker/settings
- **Secrets设置**: https://github.com/caiclhy0806/fx-tracker/settings/secrets/actions
- **Actions页面**: https://github.com/caiclhy0806/fx-tracker/actions
- **126邮箱设置**: https://mail.126.com

---

**预计完成时间**: 10-15分钟（包括获取授权码的时间）

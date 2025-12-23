# Git 安装与 GitHub 项目关联指南

## 一、安装 Git

### 1. 下载 Git 安装包
访问 Git 官方网站下载适合 Windows 系统的安装包：
- 官方下载地址：https://git-scm.com/download/
- 点击 "Downloads for Windows" 按钮
- 根据你的 Windows 系统位数（32位或64位）选择对应的安装包

### 2. 安装 Git
运行下载好的安装包，按照以下步骤进行安装：
1. 阅读并同意许可协议，点击 "Next"
2. 选择安装路径，建议使用默认路径，点击 "Next"
3. 选择安装组件，保持默认勾选即可，点击 "Next"
4. 配置开始菜单文件夹，保持默认，点击 "Next"
5. 选择 Git 默认编辑器，建议选择你熟悉的编辑器（如 VS Code），点击 "Next"
6. 选择 Git 初始化分支名称，保持默认 "main" 即可，点击 "Next"
7. 选择 Git 环境变量配置，建议选择 "Git from the command line and also from 3rd-party software"，点击 "Next"
8. 选择 SSH 客户端，保持默认 "OpenSSH" 即可，点击 "Next"
9. 选择 HTTPS 传输后端，保持默认 "OpenSSL" 即可，点击 "Next"
10. 选择换行符处理，保持默认 "Checkout Windows-style, commit Unix-style line endings" 即可，点击 "Next"
11. 选择 Git 终端模拟器，建议选择 "Git Bash only"，点击 "Next"
12. 选择 Git pull 行为，保持默认 "Default (fast-forward or merge)" 即可，点击 "Next"
13. 选择 Git Credential Manager，保持默认 "Git Credential Manager Core" 即可，点击 "Next"
14. 选择额外选项，保持默认勾选即可，点击 "Next"
15. 点击 "Install" 开始安装
16. 安装完成后，点击 "Finish"

### 3. 验证 Git 安装
打开命令提示符（CMD）或 PowerShell，运行以下命令验证 Git 是否安装成功：
```bash
git --version
```
如果显示 Git 版本信息，则表示安装成功。

## 二、关联 deep_data_agent 文件夹与 GitHub 项目

### 1. 在 GitHub 上创建项目
如果你还没有在 GitHub 上创建项目，请先创建一个：
1. 登录 GitHub
2. 点击右上角的 "+" 按钮，选择 "New repository"
3. 填写仓库名称、描述等信息
4. 选择仓库可见性（公开或私有）
5. 点击 "Create repository"

### 2. 初始化本地 Git 仓库
在命令提示符或 PowerShell 中，进入 `deep_data_agent` 文件夹：
```bash
cd d:\Code\github\deep_data_agent
```

运行以下命令初始化 Git 仓库：
```bash
git init
```

### 3. 配置 Git 用户名和邮箱
运行以下命令配置你的 Git 用户名和邮箱（用于提交记录）：
```bash
git config --global user.name "你的 GitHub 用户名"
git config --global user.email "你的 GitHub 邮箱"
```

### 4. 添加远程仓库
运行以下命令将本地仓库与 GitHub 远程仓库关联（请将 `your_username/your_repository` 替换为你的 GitHub 用户名和仓库名）：
```bash
git remote add origin https://github.com/your_username/your_repository.git
```

### 5. 提交代码到 GitHub
1. 添加所有文件到暂存区：
   ```bash
   git add .
   ```

2. 提交代码到本地仓库：
   ```bash
   git commit -m "Initial commit"
   ```

3. 推送到 GitHub 远程仓库：
   ```bash
   git push -u origin main
   ```

   如果出现认证提示，请输入你的 GitHub 用户名和密码（或使用 Personal Access Token）。

### 6. 验证关联成功
刷新 GitHub 仓库页面，你应该能看到 `deep_data_agent` 文件夹中的所有文件已经上传到 GitHub 仓库中。

## 三、后续操作

### 1. 查看 Git 状态
```bash
git status
```

### 2. 拉取远程仓库代码
```bash
git pull origin main
```

### 3. 推送本地代码到远程仓库
```bash
git push origin main
```

### 4. 查看提交历史
```bash
git log
```

## 四、常见问题

### 1. 忘记 GitHub 密码
可以使用 GitHub Personal Access Token 代替密码进行认证。

### 2. 推送失败
- 检查远程仓库地址是否正确
- 检查网络连接是否正常
- 检查是否有未提交的更改

### 3. 合并冲突
如果本地仓库与远程仓库存在冲突，需要先解决冲突，然后再提交。

## 五、参考资料
- [Git 官方文档](https://git-scm.com/doc)
- [GitHub 帮助中心](https://docs.github.com/)

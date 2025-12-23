# Git 环境变量设置指南

## 一、当前会话已解决

我已经成功将 Git 添加到了当前 PowerShell 会话的环境变量中，您现在可以正常使用 `git` 命令了。您可以通过以下命令验证：

```bash
git --version
```

## 二、永久添加 Git 到环境变量

当前的环境变量修改只对当前 PowerShell 会话有效。如果您希望在所有 PowerShell 和命令提示符会话中都能使用 `git` 命令，需要永久添加 Git 到系统环境变量中。

### 方法一：通过系统设置永久添加

1. 右键点击「此电脑」→ 选择「属性」
2. 点击「高级系统设置」→ 点击「环境变量」
3. 在「系统变量」中找到并选中「Path」→ 点击「编辑」
4. 点击「新建」→ 输入 `C:\Program Files\Git\bin` → 点击「确定」
5. 点击「新建」→ 输入 `C:\Program Files\Git\cmd` → 点击「确定」
6. 点击「确定」关闭所有对话框
7. 重新打开 PowerShell 或命令提示符，验证 `git --version` 命令是否正常工作

### 方法二：通过 PowerShell 命令永久添加（管理员权限）

1. 以管理员身份运行 PowerShell
2. 运行以下命令：
   ```powershell
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\Git\bin;C:\Program Files\Git\cmd", [EnvironmentVariableTarget]::Machine)
   ```
3. 关闭并重新打开 PowerShell，验证 `git --version` 命令是否正常工作

## 三、继续完成 GitHub 项目关联

现在您可以继续完成将 `deep_data_agent` 文件夹与 GitHub 项目关联的操作：

### 1. 初始化本地 Git 仓库

```bash
git init
```

### 2. 配置 Git 用户名和邮箱

```bash
git config --global user.name "您的 GitHub 用户名"
git config --global user.email "您的 GitHub 邮箱"
```

### 3. 添加远程仓库

将 `your_username/your_repository` 替换为您的 GitHub 用户名和仓库名：

```bash
git remote add origin https://github.com/your_username/your_repository.git
```

### 4. 提交代码到 GitHub

```bash
# 添加所有文件到暂存区
git add .

# 提交代码到本地仓库
git commit -m "Initial commit"

# 推送到 GitHub 远程仓库
git push -u origin main
```

## 四、常用 Git 命令

- 查看 Git 状态：`git status`
- 拉取远程仓库代码：`git pull origin main`
- 推送本地代码到远程仓库：`git push origin main`
- 查看提交历史：`git log`

## 五、常见问题

### 1. 推送时出现认证错误

如果推送时出现认证错误，可能是因为 GitHub 不再支持密码认证。您需要使用 Personal Access Token 代替密码：

1. 登录 GitHub
2. 点击头像 → 「Settings」→ 「Developer settings」→ 「Personal access tokens」→ 「Tokens (classic)」
3. 点击「Generate new token」→ 「Generate new token (classic)」
4. 填写 token 名称，选择有效期，勾选「repo」权限
5. 点击「Generate token」
6. 复制生成的 token，在推送时使用该 token 作为密码

### 2. 推送时出现 "fatal: refusing to merge unrelated histories"

如果出现此错误，可以使用以下命令强制推送：

```bash
git push -u origin main --force
```

### 3. 如何撤销本地提交

```bash
# 撤销最近一次提交，但保留修改
git reset --soft HEAD~1

# 撤销最近一次提交，并丢弃修改
git reset --hard HEAD~1
```

## 六、参考资料

- [Git 官方文档](https://git-scm.com/doc)
- [GitHub 帮助中心](https://docs.github.com/)

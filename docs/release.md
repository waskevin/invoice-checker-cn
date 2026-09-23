# 发布说明

本项目已配置 GitHub Actions：当推送 `v` 开头的版本标签时，会自动在 Windows 环境运行测试、打包程序、生成安装包，并创建 GitHub Release。

安装包版本号会自动取自标签，例如 `v1.0.1` 会生成版本号为 `1.0.1` 的安装包。

## 发布正式版本

在项目目录执行：

```powershell
git tag v1.0.1
git push origin v1.0.1
```

发布完成后，用户可在 GitHub Releases 页面下载 `InvoiceChecker-Setup.exe` 安装包：

https://github.com/waskevin/invoice-checker-cn/releases

## 手动触发构建

也可以在 GitHub 仓库页面进入：

`Actions` → `Build Windows Release` → `Run workflow`

手动触发只会生成构建产物，不会创建正式 Release。正式 Release 仍建议通过 `v` 开头的标签发布。

## 注意事项

- 打标签前请确认 main 分支已经包含最新代码。
- 标签名建议使用语义化版本，例如 `v1.0.1`、`v1.1.0`。
- 如果本地 Git 推送提示 SSH 权限问题，可将远程地址改为 HTTPS：

```powershell
git remote set-url origin https://github.com/waskevin/invoice-checker-cn.git
```

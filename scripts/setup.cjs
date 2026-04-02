/**
 * 跨平台一键安装入口：npm run setup
 * Windows：PowerShell 执行 scripts/setup.ps1
 * 其他：bash 执行 scripts/setup.sh
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
process.chdir(root);

const isWin = process.platform === "win32";
const script = isWin
  ? path.join(root, "scripts", "setup.ps1")
  : path.join(root, "scripts", "setup.sh");

const result = isWin
  ? spawnSync(
      "powershell",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
      { stdio: "inherit", shell: false }
    )
  : spawnSync("bash", [script], { stdio: "inherit", shell: false });

process.exit(result.status === null ? 1 : result.status);

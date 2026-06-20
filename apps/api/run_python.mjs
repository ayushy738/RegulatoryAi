import { existsSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const winVenv = join(process.cwd(), ".venv", "Scripts", "python.exe");
const posixVenv = join(process.cwd(), ".venv", "bin", "python");
const python = existsSync(winVenv) ? winVenv : existsSync(posixVenv) ? posixVenv : "python";

const result = spawnSync(python, process.argv.slice(2), {
  cwd: process.cwd(),
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);

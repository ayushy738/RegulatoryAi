# B-015 Browser Runtime Diagnosis

Date: 2026-07-30  
Host: Windows 10 Home Single Language, x64  
Codex Desktop: `OpenAI.Codex_26.721.4979.0_x64__2p2nqsd0c76g0`  
Browser plugin: `browser@openai-bundled`, build `26.721.41059`

## Outcome

The Codex in-app Browser verification environment is operational.

The repaired runtime successfully:

1. initialized the managed JavaScript kernel;
2. loaded the trusted Browser client;
3. discovered and selected the Codex In-app Browser backend;
4. created or reused a controlled tab;
5. navigated to `http://localhost:3001/ask`;
6. observed page title `Resolven Regulatory AI`;
7. captured a Playwright DOM snapshot; and
8. captured a 64,968-byte viewport screenshot.

This diagnostic did not modify Agent OS state and did not approve E9.10.

## Root Cause

B-015 was caused by a stale managed `node_repl` MCP server retaining a
per-process temporary kernel-assets directory that no longer existed.

Before every kernel launch, `node_repl.exe` writes embedded JavaScript assets
to a randomly named directory below:

```text
C:\Users\Asus\AppData\Local\Temp\.tmp*
```

The original failure occurred before user JavaScript execution:

```text
failed to write kernel assets: The system cannot find the path specified. (os error 3)
```

Windows error `3` is `ERROR_PATH_NOT_FOUND`. The failure point and error code
exclude Playwright, page navigation, application code, and browser executable
launch. A kernel reset did not recover because it resets the child kernel but
does not replace the MCP server process or its retained temporary-directory
handle.

A fresh managed MCP server created a new temporary directory and wrote all
required assets. The live process used:

```text
C:\Users\Asus\AppData\Local\Temp\.tmpEHpLvS
```

The directory contained:

- `kernel.js`
- `diagnostics.js`
- `meriyah.umd.min.js`
- `privileged-node-repl-config.js`
- `privileged-node-repl.js`
- `tracing.js`
- `trusted-process-facade.js`

After process renewal, the same repository working directory and unchanged
Codex configuration completed browser navigation successfully.

## Findings

### Runtime installation

The configured runtime exists and is complete:

```text
C:\Users\Asus\AppData\Local\OpenAI\Codex\runtimes\cua_node\f8d2abcb7481383b
```

Manifest:

- Runtime archive: `cua-node-0.0.5-20260717010102-d2131209a623-pr-1145152-windows-x64.zip`
- Node: `24.14.0`
- node_repl: `20260716.1`

Configured executables:

```text
...\bin\node.exe
...\bin\node_repl.exe
```

Both exist and execute. `node.exe --version` returns `v24.14.0`, and
`node_repl.exe --help` succeeds.

### Browser client integrity

The required client exists:

```text
C:\Users\Asus\.codex\plugins\cache\openai-bundled\browser\26.721.41059\scripts\browser-client.mjs
```

Its SHA-256 is:

```text
E13FD947E846D3D306E9249DD3C73D14931B6494803DBAFB16CEF85E6ADD9506
```

That hash is present in
`NODE_REPL_TRUSTED_BROWSER_CLIENT_SHA256S`.

### Paths and environment

The configured paths exist:

- `NODE_REPL_NODE_PATH`
- `NODE_REPL_NODE_MODULE_DIRS`
- `CODEX_CLI_PATH`
- Browser plugin client path
- `%TEMP%`
- workspace `E:\RegulatoryAi`

The managed kernel reports its working directory as:

```text
E:\RegulatoryAi
```

### Permissions

- The runtime `bin` directory grants `CodexSandboxUsers` read and execute.
- `%TEMP%` grants the sandbox identities Modify.
- The generated kernel-assets directory grants the sandbox identities Modify.
- The workspace is writable under the active Codex permission profile.

No access-denied error occurred in the managed browser path.

### Playwright

The JavaScript package is installed:

```text
playwright 1.57.0
```

Standalone Playwright-managed browser payloads are not currently installed;
`%LOCALAPPDATA%\ms-playwright` contains only the package link registry.
This is not causal. The Browser plugin's `tab.playwright` API controls the
connected in-app browser backend and completed DOM inspection successfully.

Do not install standalone browsers merely to repair B-015.

### Installed browsers

- Google Chrome `150.0.7871.187`:
  `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
- Microsoft Edge:
  `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`

The in-app Browser backend is operational independently of those executables.

### Optional Chrome extension backend

The Chrome native-host manifest and registry entry are absent:

```text
C:\Users\Asus\AppData\Local\OpenAI\extension\com.openai.codexextension.json
HKCU\Software\Google\Chrome\NativeMessagingHosts\com.openai.codexextension
```

This affects the optional Chrome-extension backend only. It does not affect
the selected Codex In-app Browser and did not cause B-015.

### Nested sandbox diagnostic

Launching `node_repl.exe` manually from an already restricted
`CodexSandboxOffline` shell and allowing it to create another restricted token
fails with:

```text
CreateRestrictedToken failed: 87
```

The same executable succeeds with its documented `--disable-sandbox`
diagnostic flag, and it succeeds normally when launched by Codex Desktop under
the normal desktop user. The nested-shell result is a diagnostic artifact and
is not the production repair. Do not add `--disable-sandbox` to the persistent
configuration while the managed launch path works.

## Reproduction

The original failure reproduces when all of the following are true:

1. the `node_repl` MCP server remains alive;
2. its process-owned `%TEMP%\.tmp*` kernel-assets directory has disappeared;
3. a new JavaScript kernel is requested; and
4. only the child kernel is reset, leaving the stale MCP server alive.

The request then fails before evaluating even:

```javascript
nodeRepl.write({ ok: true })
```

with Windows error `3`.

## Restoration Procedure

### Preferred procedure

1. Save or finish any active Codex task.
2. Exit Codex Desktop completely.
3. Confirm no stale `node_repl.exe` remains:

```powershell
Get-Process -Name node_repl -ErrorAction SilentlyContinue
```

4. If a stale process remains, stop only that process:

```powershell
Get-Process -Name node_repl -ErrorAction SilentlyContinue |
  Stop-Process -Force
```

5. Relaunch Codex Desktop:

```powershell
Start-Process explorer.exe `
  'shell:AppsFolder\OpenAI.Codex_2p2nqsd0c76g0!App'
```

6. Retry a minimal managed JavaScript execution.
7. Initialize the Browser client and navigate to the local verification URL.

Do not manually recreate the random `%TEMP%\.tmp*` directory. It is owned by
the `node_repl` process lifecycle and must be regenerated by a fresh server.

### Runtime-path preflight

```powershell
$runtime = 'C:\Users\Asus\AppData\Local\OpenAI\Codex\runtimes\cua_node\f8d2abcb7481383b\bin'
$client = 'C:\Users\Asus\.codex\plugins\cache\openai-bundled\browser\26.721.41059\scripts\browser-client.mjs'

Test-Path "$runtime\node.exe"
Test-Path "$runtime\node_repl.exe"
Test-Path "$runtime\node_modules"
Test-Path $client
Test-Path $env:TEMP

& "$runtime\node.exe" --version
& "$runtime\node_repl.exe" --help
Get-FileHash -Algorithm SHA256 $client
```

Every `Test-Path` result must be `True`. The client hash must be included in
`NODE_REPL_TRUSTED_BROWSER_CLIENT_SHA256S`.

### Kernel-assets preflight

After the first successful managed JavaScript execution:

```powershell
Get-ChildItem $env:TEMP -Directory -Force -Filter '.tmp*' |
  Sort-Object LastWriteTime -Descending |
  ForEach-Object {
    if (Test-Path (Join-Path $_.FullName 'kernel.js')) {
      Get-ChildItem $_.FullName -Force
      break
    }
  }
```

The seven runtime asset files listed above must be present.

### Browser verification

Run the application:

```powershell
npm.cmd run dev --workspace @regulatory-ai/web -- --host localhost --port 3001
```

Then use the managed Browser client to:

1. select the browser for `http://localhost:3001/ask`;
2. open the URL;
3. wait for `domcontentloaded`;
4. confirm title `Resolven Regulatory AI`;
5. capture a DOM snapshot; and
6. capture a screenshot.

## Non-Repairs

The following actions are not required for B-015:

- changing repository application code;
- modifying Agent OS documents;
- installing standalone Playwright browsers;
- installing or repairing the Chrome extension native host;
- changing the working directory;
- changing browser executable paths;
- adding `--disable-sandbox` to persistent MCP configuration.

## Verification Result

PASS — the managed Codex In-app Browser navigated to the local Ask AI
application and completed Playwright DOM inspection and screenshot capture.


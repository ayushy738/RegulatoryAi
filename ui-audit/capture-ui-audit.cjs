const fs = require("fs");
const http = require("http");
const net = require("net");
const crypto = require("crypto");
const { spawn } = require("child_process");
const { URL } = require("url");

const chromePath = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe";
const outDir = "e:\\RegulatoryAi\\ui-audit";
const profileDir = `${outDir}\\chrome-profile`;
const port = 9223;
const routes = [
  { name: "landing", url: "http://localhost:3000/landing" },
  { name: "dashboard", url: "http://localhost:3000/dashboard" },
  { name: "ask", url: "http://localhost:3000/ask" },
  { name: "account", url: "http://localhost:3000/account" },
  { name: "admin", url: "http://localhost:3000/admin" },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestJson(method, path) {
  return new Promise((resolve, reject) => {
    const req = http.request({ method, hostname: "127.0.0.1", port, path }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on("error", reject);
    req.end();
  });
}

function encodeFrame(payload) {
  const data = Buffer.from(payload);
  const mask = crypto.randomBytes(4);
  let header;
  if (data.length < 126) {
    header = Buffer.from([0x81, 0x80 | data.length]);
  } else if (data.length < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 0x80 | 126;
    header.writeUInt16BE(data.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 0x80 | 127;
    header.writeBigUInt64BE(BigInt(data.length), 2);
  }
  const masked = Buffer.alloc(data.length);
  for (let i = 0; i < data.length; i += 1) masked[i] = data[i] ^ mask[i % 4];
  return Buffer.concat([header, mask, masked]);
}

function decodeFrames(buffer) {
  const frames = [];
  let offset = 0;
  while (buffer.length - offset >= 2) {
    const byte1 = buffer[offset];
    const byte2 = buffer[offset + 1];
    let length = byte2 & 0x7f;
    let headerLength = 2;
    if (length === 126) {
      if (buffer.length - offset < 4) break;
      length = buffer.readUInt16BE(offset + 2);
      headerLength = 4;
    } else if (length === 127) {
      if (buffer.length - offset < 10) break;
      length = Number(buffer.readBigUInt64BE(offset + 2));
      headerLength = 10;
    }
    const masked = Boolean(byte2 & 0x80);
    const maskLength = masked ? 4 : 0;
    const frameLength = headerLength + maskLength + length;
    if (buffer.length - offset < frameLength) break;
    const opcode = byte1 & 0x0f;
    const mask = masked ? buffer.subarray(offset + headerLength, offset + headerLength + 4) : null;
    const payloadStart = offset + headerLength + maskLength;
    const payload = Buffer.from(buffer.subarray(payloadStart, payloadStart + length));
    if (mask) {
      for (let i = 0; i < payload.length; i += 1) payload[i] ^= mask[i % 4];
    }
    if (opcode === 1) frames.push(payload.toString("utf8"));
    offset += frameLength;
  }
  return { frames, rest: buffer.subarray(offset) };
}

function connectWs(wsUrl) {
  const parsed = new URL(wsUrl);
  let socket;
  let nextId = 1;
  let pending = new Map();
  let buffer = Buffer.alloc(0);
  const key = crypto.randomBytes(16).toString("base64");
  return new Promise((resolve, reject) => {
    socket = net.connect(Number(parsed.port), parsed.hostname, () => {
      socket.write(
        [
          `GET ${parsed.pathname}${parsed.search} HTTP/1.1`,
          `Host: ${parsed.host}`,
          "Upgrade: websocket",
          "Connection: Upgrade",
          `Sec-WebSocket-Key: ${key}`,
          "Sec-WebSocket-Version: 13",
          "",
          "",
        ].join("\r\n"),
      );
    });
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (!socket.upgraded) {
        const marker = buffer.indexOf("\r\n\r\n");
        if (marker === -1) return;
        const head = buffer.subarray(0, marker).toString();
        if (!head.includes("101")) {
          reject(new Error(`WebSocket upgrade failed: ${head}`));
          return;
        }
        socket.upgraded = true;
        buffer = buffer.subarray(marker + 4);
        resolve({
          send(method, params = {}) {
            const id = nextId++;
            socket.write(encodeFrame(JSON.stringify({ id, method, params })));
            return new Promise((res, rej) => pending.set(id, { res, rej }));
          },
          close() {
            socket.end();
          },
        });
      }
      if (socket.upgraded && buffer.length) {
        const decoded = decodeFrames(buffer);
        buffer = decoded.rest;
        for (const text of decoded.frames) {
          const message = JSON.parse(text);
          if (message.id && pending.has(message.id)) {
            const item = pending.get(message.id);
            pending.delete(message.id);
            if (message.error) item.rej(new Error(JSON.stringify(message.error)));
            else item.res(message.result);
          }
        }
      }
    });
    socket.on("error", reject);
  });
}

async function waitForChrome() {
  for (let i = 0; i < 50; i += 1) {
    try {
      await requestJson("GET", "/json/version");
      return;
    } catch (_) {
      await sleep(200);
    }
  }
  throw new Error("Chrome DevTools did not start.");
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result.result.value;
}

async function captureRoute(chrome, route) {
  const target = await requestJson("PUT", `/json/new?${encodeURIComponent(route.url)}`);
  const cdp = await connectWs(target.webSocketDebuggerUrl);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1200,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await sleep(2500);
  const clickedPreview = await evaluate(
    cdp,
    `(() => {
      const btn = [...document.querySelectorAll('button')].find((button) =>
        /Continue Local Preview/i.test(button.textContent || '')
      );
      if (btn) btn.click();
      return Boolean(btn);
    })()`,
  );
  await sleep(clickedPreview ? 4500 : 2500);
  await evaluate(
    cdp,
    `new Promise((resolve) => {
      const done = () => resolve(document.readyState);
      if (document.readyState === 'complete') done();
      else window.addEventListener('load', done, { once: true });
      setTimeout(done, 3000);
    })`,
  );
  await sleep(1500);
  const findings = await evaluate(
    cdp,
    `(() => {
      const text = document.body.innerText || '';
      const q = (selector) => [...document.querySelectorAll(selector)];
      const rect = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) };
      };
      const visibleText = (selector) => q(selector).map((el) => (el.textContent || '').trim()).filter(Boolean);
      return {
        title: document.title,
        url: location.href,
        bodySnippet: text.slice(0, 900),
        headings: visibleText('h1,h2,h3').slice(0, 30),
        navItems: visibleText('nav a, aside.sidebar a').slice(0, 20),
        counts: {
          stitchClasses: q('[class*="stitch-"]').length,
          cards: q('[class*="card"]').length,
          panels: q('[class*="panel"]').length,
          sections: q('section').length,
          buttons: q('button').length,
          links: q('a').length,
          inputs: q('input, textarea, select').length,
          materialIcons: q('.material-symbols-outlined').length,
          errorStates: q('.state-block.error, [class*="error"]').length,
        },
        keyRects: {
          shell: rect('.app-shell'),
          sidebar: rect('.sidebar'),
          topbar: rect('.topbar'),
          dashboard: rect('.stitch-dashboard'),
          ask: rect('.stitch-ask-page'),
          landing: rect('.stitch-landing'),
          account: rect('.two-column'),
          admin: rect('.stitch-admin-page'),
          auth: rect('.auth-card'),
        },
        hasAuthGate: /Sign in|Continue Local Preview|Send Magic Link/i.test(text),
        hasApiError: /Unable to load|Failed to fetch|error/i.test(text),
        hasLoading: /Loading|Thinking/i.test(text),
      };
    })()`,
  );
  const png = await cdp.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: true,
  });
  const screenshotPath = `${outDir}\\${route.name}.png`;
  fs.writeFileSync(screenshotPath, Buffer.from(png.data, "base64"));
  fs.writeFileSync(`${outDir}\\${route.name}.dom.json`, JSON.stringify(findings, null, 2));
  cdp.close();
  return { ...route, screenshotPath, findings };
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  fs.rmSync(profileDir, { recursive: true, force: true });
  const chrome = spawn(chromePath, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--disable-default-apps",
    "about:blank",
  ], { stdio: "ignore" });
  try {
    await waitForChrome();
    const results = [];
    for (const route of routes) results.push(await captureRoute(chrome, route));
    fs.writeFileSync(`${outDir}\\ui-audit-results.json`, JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results.map((item) => ({
      name: item.name,
      screenshotPath: item.screenshotPath,
      headings: item.findings.headings.slice(0, 6),
      counts: item.findings.counts,
      hasAuthGate: item.findings.hasAuthGate,
      hasApiError: item.findings.hasApiError,
    })), null, 2));
  } finally {
    chrome.kill();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

import { createWriteStream, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { spawn } from "node:child_process";

const [logFile, command, ...args] = process.argv.slice(2);

if (!logFile || !command) {
  console.error("Usage: node run-with-log.mjs <log-file> <command> [...args]");
  process.exit(2);
}

const absoluteLogFile = resolve(logFile);
mkdirSync(dirname(absoluteLogFile), { recursive: true });

const log = createWriteStream(absoluteLogFile, { flags: "a" });
const sessionHeader = `\n\n===== ${new Date().toISOString()} | ${command} ${args.join(" ")} =====\n`;
log.write(sessionHeader);
console.log(`Writing this session to ${absoluteLogFile}`);

const child = spawn(command, args, {
  cwd: process.cwd(),
  env: process.env,
  stdio: ["inherit", "pipe", "pipe"],
  windowsHide: false,
});

function mirror(source, destination) {
  source.on("data", (chunk) => {
    destination.write(chunk);
    log.write(chunk);
  });
}

mirror(child.stdout, process.stdout);
mirror(child.stderr, process.stderr);

child.on("error", (error) => {
  const message = `Could not start ${command}: ${error.message}\n`;
  process.stderr.write(message);
  log.end(message);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  const result = `\n===== process ended | code=${code ?? "none"} signal=${signal ?? "none"} =====\n`;
  log.end(result);
  process.exitCode = code ?? (signal ? 1 : 0);
});

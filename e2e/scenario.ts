import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";

export const backendUrl = "http://127.0.0.1:8001";

export function startScenario(
  claimId: string,
  outcome: string,
  amount: string,
  pause = false,
) {
  const args = ["run", "-m", "agent.tests.scenario", claimId, outcome, amount];
  if (pause) args.push("--pause");
  const executable =
    process.env.UV_EXECUTABLE ??
    join(
      homedir(),
      ".local",
      "bin",
      process.platform === "win32" ? "uv.exe" : "uv",
    );
  const child = spawn(executable, args, {
    env: { ...process.env, BACKEND_URL: backendUrl },
    timeout: 60000,
  });
  let output = "";
  let errorOutput = "";
  let release: () => void;
  let rejectReady: (reason: Error) => void;
  const ready = new Promise<void>((resolve, reject) => {
    release = resolve;
    rejectReady = reject;
  });
  child.stdout.on("data", (chunk: Buffer) => {
    output += chunk.toString();
    if (output.includes("READY")) release();
  });
  child.stderr.on("data", (chunk: Buffer) => {
    errorOutput += chunk.toString();
  });
  const completion = new Promise<void>((resolve, reject) => {
    child.on("error", (error) => {
      reject(error);
      rejectReady(error);
    });
    child.on("close", (code) => {
      if (code === 0) {
        release();
        resolve();
      } else {
        const error = new Error(
          `Scripted agent failed (${String(code)}): ${errorOutput}`,
        );
        reject(error);
        rejectReady(error);
      }
    });
  });
  void ready.catch(() => undefined);
  void completion.catch(() => undefined);
  return {
    ready,
    completion,
    resume: () => {
      child.stdin.end("continue\n");
    },
    stop: () => {
      child.kill();
    },
  };
}

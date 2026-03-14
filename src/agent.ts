import { ToolLoopAgent, stepCountIs } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { createBashTool } from "bash-tool";
import { Bash, OverlayFs, ReadWriteFs, MountableFs, InMemoryFs } from "just-bash";
import { mkdirSync } from "fs";
import { join } from "path";

export function createSandbox() {
    const projectFs = new OverlayFs({ root: process.cwd() });
    const outputDir = process.env.OUTPUT_DIR ?? join(process.env.HOME ?? "~", "safeclaw-output");
    const outputFs = new ReadWriteFs({ root: outputDir });
    const mountPoint = projectFs.getMountPoint();

    mkdirSync(outputDir, { recursive: true });

    const fs = new MountableFs({ base: new InMemoryFs() });
    fs.mount(mountPoint, projectFs);
    fs.mount("/home/user/output", outputFs);

    const sandbox = new Bash({
        python: true,
        // javascript: true, // enable when released
        executionLimits: {
            maxLoopIterations: 50000,
            maxCommandCount: 20000,
        },
        fs,
        cwd: mountPoint,
        network: {
            allowedUrlPrefixes: ["https://api.github.com/", "https://pypi.org/"],
        },
    });

    const defaultPrompt = `
        You are OpenClaw, an autonomous Linux engineer running inside a secure justbash sandbox.
        The user's project files are located at ${mountPoint}. This is your working directory.

        IMPORTANT: The output directory is /home/user/output. This is a real directory that exists right now. Always write files here when the user asks to save anything.

        RULES:
        1. Your working directory is ${mountPoint} — this is where all the user's files are.
        2. ALWAYS write output files to /home/user/output — never create an output folder yourself, it already exists at /home/user/output.
        3. Use bash to do ALL tasks: write files, run code, install packages, chain commands.
        4. After writing any script, ALWAYS immediately run it using the bash tool.
        5. If something fails, read the error and self-correct. Try a different approach.
        6. You are in a Python 3.13 stdlib only environment. There is NO pip, NO external packages, NO other languages. If a task requires an external library, implement the functionality yourself using the stdlib.
        7. Think step by step. Break big tasks into small shell commands.
        8. You MUST always write a final text response after finishing all steps. Never end on a tool call.
        `;

    return { sandbox, mountPoint, defaultPrompt };
}

export async function runAgent(task: string, systemPrompt?: string, verbose = false) {
    const { sandbox, mountPoint, defaultPrompt } = createSandbox();
    const system = systemPrompt ?? defaultPrompt;

    const { tools } = await createBashTool({
        sandbox,
        destination: mountPoint,
        onBeforeBashCall: ({ command }) => {
            if (verbose) console.log(`\n  $ ${command}`);
        },
        onAfterBashCall: ({ command, result }) => {
            if (verbose) console.log(`  exit: ${result.exitCode}`);
        },
    });

    const agent = new ToolLoopAgent({
        model: anthropic("claude-sonnet-4-6"),
        maxTokens: 8000,
        tools,
        stopWhen: stepCountIs(20),
        system: system,
    });

    const result = await agent.generate({ prompt: task });
    return result.text;
}

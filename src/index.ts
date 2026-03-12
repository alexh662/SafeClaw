#!/usr/bin/env tsx

import * as readline from "node:readline/promises";
import { ToolLoopAgent, stepCountIs } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { createBashTool } from "bash-tool";
import { type ModelMessage } from "ai";
import { setup } from "./env-setup.js";
import { createSandbox } from "./agent.js";

if (process.argv.includes("--server")) {
    await import("./server.js");
} else {
    await setup();

    const { sandbox, mountPoint, defaultPrompt: systemPrompt } = createSandbox();

    let verbose = process.argv.includes("--print-bash");

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

    const messages: ModelMessage[] = [];

    // create readline interface for user input
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    // create agent
    const agent = new ToolLoopAgent({
        model: anthropic("claude-sonnet-4-6"),
        tools,
        stopWhen: stepCountIs(20),
        system: systemPrompt,
    });

    // handle ctrl+c gracefully
    process.on("SIGINT", () => {
        rl.close();
        process.exit(0);
    });

    async function main() {
        console.log("SafeClaw ready. Type 'exit' or use Ctrl+C to quit. Type '/print-bash' to toggle bash output or '/reset' to reset the conversation.\n");

        while (true) {
            let userInput: string;

            try {
                userInput = await rl.question("You: ");
            } catch {
                process.exit(0);
            }

            if (userInput.toLowerCase() === "exit") {
                break;
            }

            if (!userInput.trim()) continue;

            if (userInput === "/print-bash") {
                verbose = !verbose;
                console.log(`Bash output ${verbose ? "shown" : "not shown"}`);
                continue;
            }

            if (userInput === "/reset") {
                messages.length = 0;
                console.log("Conversation reset.");
                continue;
            }

            process.stdout.write("\nSafeClaw: Thinking...");

            try {
                messages.push({ role: "user", content: userInput });
                const result = await agent.generate({ prompt: messages });
                messages.push({ role: "assistant", content: result.text });

                console.log(`\nSafeClaw: ${result.text}\n`);

                // for debugging:
                // console.log("result keys:", Object.keys(result));
                // console.log("result.text:", JSON.stringify(result.text));
                // console.log("steps:", (result as any).steps?.length);
                // console.log("full result:", JSON.stringify(result, null, 2).slice(0, 1000));

            } catch (error) {
                console.error("\nError:", error);
            }
        }

        rl.close();
    }

    main();
}

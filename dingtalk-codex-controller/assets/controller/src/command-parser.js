import { ControllerError } from "./errors.js";
import { codePointLength } from "./util.js";

const CONTROL_CHARACTERS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/u;
const ACTION_ALIAS = /^[a-z0-9][a-z0-9-]{0,62}$/u;
const REQUEST_ID = /^REQ-[0-9]{14}-[a-f0-9]{8}$/u;
const THREAD_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/iu;
const THREAD_PAGE = /^[1-9][0-9]{0,2}$/u;
const RESERVED_COMMANDS = new Set([
  "help", "status", "threads", "send", "run", "result",
  "bind", "target", "watch", "queue", "cancel"
]);

function requireInstruction(value, maxInstructionCodePoints) {
  const instruction = value.trim();
  if (!instruction) {
    throw new ControllerError("COMMAND_INVALID", "Instruction must not be empty");
  }
  if (codePointLength(instruction) > maxInstructionCodePoints) {
    throw new ControllerError("INSTRUCTION_TOO_LONG", "Instruction exceeds the configured length limit");
  }
  return instruction;
}

function parseSendArguments(value) {
  const quoted = value.match(/^"([^"]+)"[\t \n]+([\s\S]+)$/u);
  if (quoted) return { selector: quoted[1].trim(), instruction: quoted[2] };
  const unquoted = value.match(/^([^\s]+)[\t \n]+([\s\S]+)$/u);
  if (unquoted) return { selector: unquoted[1].trim(), instruction: unquoted[2] };
  throw new ControllerError("COMMAND_INVALID", "Command does not match the supported grammar");
}

function requireSelector(value) {
  const selector = value.trim();
  if (!selector || codePointLength(selector) > 120 || CONTROL_CHARACTERS.test(selector)) {
    throw new ControllerError("COMMAND_INVALID", "Task selector is invalid");
  }
  return selector;
}

export function parseCommand(input, options = {}) {
  const maxCodePoints = options.maxCodePoints ?? 128;
  const maxInstructionCodePoints = options.maxInstructionCodePoints ?? 1000;
  if (typeof input !== "string") {
    throw new ControllerError("COMMAND_NOT_TEXT", "Command must be text");
  }

  const normalized = input.replace(/\r\n?/g, "\n").trimStart().trimEnd();
  if (CONTROL_CHARACTERS.test(normalized)) {
    throw new ControllerError("COMMAND_CONTROL_CHARACTER", "Command contains unsupported control characters");
  }
  if (!normalized.startsWith("/codex")) {
    return { kind: "not-command" };
  }

  const tokens = normalized.split(/\s+/u);
  if (tokens[0] !== "/codex") {
    return { kind: "not-command" };
  }

  if (tokens[1] === "send") {
    const value = normalized.replace(/^\/codex[\t ]+send[\t ]+/u, "");
    const parsed = parseSendArguments(value);
    const selector = requireSelector(parsed.selector);
    const command = {
      kind: "command",
      command: "send",
      instruction: requireInstruction(parsed.instruction, maxInstructionCodePoints)
    };
    if (THREAD_ID.test(selector)) command.targetThreadId = selector.toLowerCase();
    else command.targetSelector = selector;
    return command;
  }

  if (codePointLength(normalized) > maxCodePoints) {
    throw new ControllerError("COMMAND_TOO_LONG", "Command exceeds the configured length limit");
  }

  if (tokens.length === 2 && tokens[1] === "help") {
    return { kind: "command", command: "help" };
  }
  if (tokens.length === 2 && tokens[1] === "status") {
    return { kind: "command", command: "status" };
  }
  if (tokens.length === 2 && tokens[1] === "threads") {
    return { kind: "command", command: "threads", page: 1 };
  }
  if (tokens.length === 3 && tokens[1] === "threads" && THREAD_PAGE.test(tokens[2])) {
    return { kind: "command", command: "threads", page: Number(tokens[2]) };
  }
  if (tokens.length === 3 && tokens[1] === "run" && ACTION_ALIAS.test(tokens[2])) {
    return { kind: "command", command: "run", actionAlias: tokens[2] };
  }
  if (tokens.length === 2 && tokens[1] === "result") {
    return { kind: "command", command: "result", requestId: null };
  }
  if (tokens.length === 3 && tokens[1] === "result" && REQUEST_ID.test(tokens[2])) {
    return { kind: "command", command: "result", requestId: tokens[2] };
  }
  if (tokens.length === 2 && new Set(["bind", "target"]).has(tokens[1])) {
    return { kind: "command", command: "target", targetSelector: null };
  }
  if (new Set(["bind", "target"]).has(tokens[1])) {
    const selector = normalized.replace(/^\/codex[\t ]+(?:bind|target)[\t ]+/u, "");
    return { kind: "command", command: "target", targetSelector: requireSelector(selector) };
  }
  if (tokens.length === 2 && tokens[1] === "watch") {
    return { kind: "command", command: "watch", targetSelector: null };
  }
  if (tokens[1] === "watch") {
    const selector = normalized.replace(/^\/codex[\t ]+watch[\t ]+/u, "");
    return { kind: "command", command: "watch", targetSelector: requireSelector(selector) };
  }
  if (tokens.length === 2 && tokens[1] === "queue") {
    return { kind: "command", command: "queue" };
  }
  if (tokens.length === 2 && tokens[1] === "cancel") {
    return { kind: "command", command: "cancel", requestId: null };
  }
  if (tokens.length === 3 && tokens[1] === "cancel" && REQUEST_ID.test(tokens[2])) {
    return { kind: "command", command: "cancel", requestId: tokens[2] };
  }

  if (RESERVED_COMMANDS.has(tokens[1])) {
    throw new ControllerError("COMMAND_INVALID", "Command does not match the supported grammar");
  }
  const instruction = normalized.slice("/codex".length).trim();
  if (instruction) {
    return {
      kind: "command",
      command: "send",
      useBoundTarget: true,
      instruction: requireInstruction(instruction, maxInstructionCodePoints)
    };
  }

  throw new ControllerError("COMMAND_INVALID", "Command does not match the supported grammar");
}

export const commandHelp = [
  "/codex help",
  "/codex status",
  "/codex threads [page]",
  "/codex target|bind [task-id|number|name|clear]",
  "/codex watch [task-id|number|name|clear]",
  "/codex send <task-id|number|\"name\"> <instruction>",
  "/codex <instruction>  (uses the bound target)",
  "/codex queue",
  "/codex cancel [request-id]",
  "/codex run <action-alias>",
  "/codex result [request-id]"
].join("\n");

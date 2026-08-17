export type InputMode = "flash" | "thinking" | "pro" | "ultra";

export function resolveInputMode(
  mode: InputMode | undefined,
  supportsThinking: boolean,
): InputMode {
  if (!supportsThinking && mode !== "flash") {
    return "flash";
  }
  if (mode) {
    return mode;
  }
  return supportsThinking ? "thinking" : "flash";
}

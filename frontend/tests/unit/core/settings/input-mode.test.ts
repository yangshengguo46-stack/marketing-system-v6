import { expect, test } from "@rstest/core";

import { resolveInputMode } from "@/core/settings/input-mode";

test("defaults thinking-capable models to thinking without plan mode", () => {
  expect(resolveInputMode(undefined, true)).toBe("thinking");
});

test("keeps an explicit mode selection", () => {
  expect(resolveInputMode("pro", true)).toBe("pro");
  expect(resolveInputMode("ultra", true)).toBe("ultra");
});

test("falls back to flash when the model cannot think", () => {
  expect(resolveInputMode(undefined, false)).toBe("flash");
  expect(resolveInputMode("thinking", false)).toBe("flash");
});

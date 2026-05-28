import { afterEach, describe, expect, it, vi } from "vitest";
import { createUuid, sha256Hex } from "@/utils/browserCrypto";

describe("browser crypto compatibility helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hashes with the JavaScript fallback when WebCrypto is unavailable", async () => {
    vi.stubGlobal("crypto", undefined);

    await expect(sha256Hex("abc")).resolves.toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  it("generates an RFC 4122 UUID when randomUUID is unavailable", () => {
    vi.stubGlobal("crypto", {
      getRandomValues(target: Uint8Array) {
        target.set([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
        return target;
      },
    });

    expect(createUuid()).toBe("00010203-0405-4607-8809-0a0b0c0d0e0f");
  });
});

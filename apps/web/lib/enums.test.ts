import { describe, expect, it } from "vitest";
import { leadStatusMeta, callStatusMeta, campaignStatusMeta } from "./enums";

describe("enum label/tone mapping", () => {
  it("maps known backend enum values to Turkish labels", () => {
    expect(leadStatusMeta("do_not_call")).toEqual({ label: "Aranmasın", tone: "danger" });
    expect(callStatusMeta("agent_active").tone).toBe("brand");
    expect(campaignStatusMeta("running").tone).toBe("success");
  });

  it("falls back to a neutral badge with the raw value for unknown enum values", () => {
    // Backend enum'u güncellenip panel güncellenmezse UI çökmemeli.
    expect(leadStatusMeta("some_future_status")).toEqual({
      label: "some_future_status",
      tone: "neutral",
    });
  });
});

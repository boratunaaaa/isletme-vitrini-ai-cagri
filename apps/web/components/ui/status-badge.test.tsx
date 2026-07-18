import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("renders the label text", () => {
    render(<StatusBadge label="Tamamlandı" tone="success" />);
    expect(screen.getByText("Tamamlandı")).toBeInTheDocument();
  });
});

// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskAirView } from "./AskAirView";
import { askCopilot, getCopilotStatus, type CopilotReply } from "../../api/copilot";

vi.mock("../../api/copilot", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../../api/copilot")>();
  return {
    ...original,
    askCopilot: vi.fn(),
    getCopilotStatus: vi.fn(),
  };
});

const mockedAsk = vi.mocked(askCopilot);
const mockedStatus = vi.mocked(getCopilotStatus);

const reply: CopilotReply = {
  answer: "The forecast rises during a low-dispersion period.",
  evidence: ["The selected forecast peaks at 61.7 µg/m³."],
  data_status: "station-corrected",
  limitations: ["FIRMS is unavailable for this snapshot."],
  suggested_questions: ["What actions are recommended?"],
};

function renderCopilot(overrides: Partial<React.ComponentProps<typeof AskAirView>> = {}) {
  return render(
    <AskAirView
      cityName="Delhi NCR"
      cityId="delhi-ncr"
      pollutant="pm2_5"
      horizon={24}
      snapshotId="snapshot-delhi"
      {...overrides}
    />,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  mockedAsk.mockReset();
  mockedStatus.mockReset();
  mockedStatus.mockResolvedValue({
    enabled: true,
    configured: true,
    provider: "Google Gemini",
    model: "gemini-2.5-flash",
  });
});

afterEach(() => cleanup());

describe("AskAirView", () => {
  it("opens, shows the current context and suggested questions, and closes", async () => {
    renderCopilot();
    fireEvent.click(screen.getByRole("button", { name: "Open Ask AirView" }));
    expect(screen.getByRole("dialog", { name: "Ask AirView" })).toBeTruthy();
    expect(screen.getByText("Delhi NCR · PM2.5 · Next 24 hours")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Why is the forecast rising?" })).toBeTruthy();
    expect(document.querySelector(".ask-airview-panel")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close Ask AirView" }));
    expect(screen.queryByRole("dialog", { name: "Ask AirView" })).toBeNull();
  });

  it("shows loading and renders a successful structured response", async () => {
    let resolveRequest: (value: CopilotReply) => void = () => undefined;
    mockedAsk.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
    renderCopilot();
    fireEvent.click(screen.getByRole("button", { name: "Open Ask AirView" }));
    fireEvent.click(screen.getByRole("button", { name: "Why is the forecast rising?" }));
    expect(screen.getByRole("status").textContent).toContain("Preparing a grounded answer");
    await act(async () => resolveRequest(reply));
    expect(await screen.findByText(reply.answer)).toBeTruthy();
    expect(screen.getByText("station-corrected")).toBeTruthy();
    expect(screen.getByText(reply.evidence[0])).toBeTruthy();
    expect(mockedAsk.mock.calls[0][0]).toMatchObject({
      city_id: "delhi-ncr",
      pollutant: "pm2_5",
      horizon: 24,
      snapshot_id: "snapshot-delhi",
    });
  });

  it("shows a concise retry state for provider failure", async () => {
    mockedAsk.mockRejectedValue(new Error("provider stack trace"));
    renderCopilot();
    fireEvent.click(screen.getByRole("button", { name: "Open Ask AirView" }));
    fireEvent.change(screen.getByLabelText("Question for Ask AirView"), {
      target: { value: "Summarise the evidence." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("temporarily unavailable");
    expect(alert.textContent).not.toContain("stack trace");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("updates context and ignores a response from the previous snapshot", async () => {
    let resolveRequest: (value: CopilotReply) => void = () => undefined;
    mockedAsk.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
    const view = renderCopilot();
    fireEvent.click(screen.getByRole("button", { name: "Open Ask AirView" }));
    fireEvent.click(screen.getByRole("button", { name: "Why is the forecast rising?" }));
    view.rerender(
      <AskAirView
        cityName="Ludhiana"
        cityId="ludhiana"
        pollutant="pm10"
        horizon={72}
        snapshotId="snapshot-ludhiana"
      />,
    );
    expect(screen.getByText("Ludhiana · PM10 · Next 72 hours")).toBeTruthy();
    expect(screen.getByText("Context updated to Ludhiana · PM10 · Next 72 hours.")).toBeTruthy();
    await act(async () => resolveRequest(reply));
    await waitFor(() => expect(screen.queryByText(reply.answer)).toBeNull());
  });

  it("shows the configured-unavailable state without exposing details", async () => {
    mockedStatus.mockResolvedValue({
      enabled: true,
      configured: false,
      provider: "Google Gemini",
      model: "gemini-2.5-flash",
    });
    renderCopilot();
    fireEvent.click(screen.getByRole("button", { name: "Open Ask AirView" }));
    expect(await screen.findByText("Ask AirView is unavailable on this deployment.")).toBeTruthy();
  });
});

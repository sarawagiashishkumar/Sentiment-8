import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { SessionHealthIndicator } from "./SessionHealthIndicator";

jest.mock("axios", () => ({ get: jest.fn() }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("SessionHealthIndicator", () => {
  let container;
  let root;

  beforeEach(() => {
    jest.useFakeTimers();
    axios.get.mockReset();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.useRealTimers();
  });

  it("confirms a transient failure before showing offline", async () => {
    axios.get
      .mockRejectedValueOnce(new Error("temporary timeout"))
      .mockResolvedValueOnce({ data: { status: "healthy" } });

    await act(async () => {
      root.render(<SessionHealthIndicator />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelector("[data-testid='session-health-indicator']").dataset.healthStatus).toBe("degraded");

    await act(async () => {
      jest.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelector("[data-testid='session-health-indicator']").dataset.healthStatus).toBe("online");
    expect(axios.get).toHaveBeenCalledTimes(2);
  });
});

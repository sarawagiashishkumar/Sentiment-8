import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { AppSidebar } from "./AppSidebar";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("AppSidebar navigation", () => {
  let container;
  let root;
  let setCurrentPage;
  let onAdminClick;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    setCurrentPage = jest.fn();
    onAdminClick = jest.fn();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  it("routes every visible menu item to its matching dashboard page", async () => {
    await act(async () => {
      root.render(
        <AppSidebar
          currentPage="home"
          setCurrentPage={setCurrentPage}
          isAdmin
          onAdminClick={onAdminClick}
        />,
      );
    });

    const routes = [
      ["nav-home", "home"],
      ["nav-multibagger", "multibagger"],
      ["nav-fno-projections", "fno"],
      ["nav-portfolio", "portfolio"],
      ["nav-heatmap", "heatmap"],
      ["nav-reports", "reports"],
      ["nav-watchlist", "watchlist"],
      ["nav-plans", "plans"],
      ["nav-admin", "admin"],
    ];

    for (const [testId, page] of routes) {
      await act(async () => {
        container.querySelector(`[data-testid="${testId}"]`).click();
      });
      expect(setCurrentPage).toHaveBeenLastCalledWith(page);
    }

    expect(setCurrentPage).toHaveBeenCalledTimes(routes.length);
    expect(onAdminClick).toHaveBeenCalledTimes(1);
  });
});

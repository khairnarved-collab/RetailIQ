import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { EmptyState, ErrorState, KpiCard, StatusBadge } from "@/components/common";
import { AuthProvider } from "@/hooks/useAuth";
import { ThemeProvider } from "@/hooks/useTheme";
import { Login } from "@/pages/AuthPages";
import { api, ApiError } from "@/services/api";

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((q: string) => ({ matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  });
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return render(
    <ThemeProvider><QueryClientProvider client={qc}><AuthProvider><TooltipProvider><MemoryRouter>{ui}</MemoryRouter></TooltipProvider></AuthProvider></QueryClientProvider></ThemeProvider>,
  );
}

describe("shared components", () => {
  it("status badge always shows a text label (not colour alone)", () => {
    render(<StatusBadge status="Critical" />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });
  it("KPI card shows value and growth", () => {
    render(<TooltipProvider><KpiCard label="Total Revenue" value="$1,000" delta={5} /></TooltipProvider>);
    expect(screen.getByText("$1,000")).toBeInTheDocument();
    expect(screen.getByText(/\+5\.0% vs prev\. period/)).toBeInTheDocument();
  });
  it("error state offers a retry", async () => {
    const retry = vi.fn();
    render(<ErrorState error={new Error("boom")} onRetry={retry} />);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(retry).toHaveBeenCalled();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
  it("empty state renders title and description", () => {
    render(<EmptyState title="Nothing here" description="Upload data" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});

describe("login page", () => {
  it("shows the form, demo accounts and an error on failed login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Incorrect email or password" }), { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    wrap(<Login />);
    expect(screen.getByRole("button", { name: "Admin demo" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "x@y.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrongpass1");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/login", expect.objectContaining({ method: "POST" }));
    vi.unstubAllGlobals();
  });
});

describe("api client", () => {
  it("sends the bearer token and turns API errors into ApiError", async () => {
    localStorage.setItem("retailiq-token", "abc");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not allowed" }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.get("/admin/users")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer abc");
    vi.unstubAllGlobals();
  });
});

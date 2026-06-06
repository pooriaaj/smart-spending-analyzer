import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n/LanguageContext";
import api from "../services/api";
import AccountsPage from "./AccountsPage";

const { mockNavigate, mockHandleApiAuthError } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockHandleApiAuthError: vi.fn(() => false),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");

  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../services/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  handleApiAuthError: mockHandleApiAuthError,
}));

function renderAccountsPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AccountsPage />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

describe("AccountsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: {
        accounts: [
          {
            id: 12,
            name: "Everyday Chequing",
            type: "chequing",
            total_income: 2500,
            total_expenses: 842.5,
            balance: 1657.5,
            top_category: "groceries",
            top_category_amount: 123.45,
          },
        ],
      },
    });
  });

  it("renders account cards from a wrapped accounts response", async () => {
    renderAccountsPage();

    expect(await screen.findByText("Everyday Chequing")).toBeInTheDocument();
    expect(screen.getAllByText("Chequing").length).toBeGreaterThan(0);
    expect(screen.getByText("$2500.00")).toBeInTheDocument();
    expect(screen.getByText("$842.50")).toBeInTheDocument();
    expect(screen.getByText("$1657.50")).toBeInTheDocument();
    expect(screen.getByText("Top category: Groceries ($123.45)")).toBeInTheDocument();
  });
});

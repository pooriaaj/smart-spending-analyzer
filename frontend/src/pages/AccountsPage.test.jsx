import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    put: vi.fn(),
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
    api.post.mockResolvedValue({ data: {} });
    api.put.mockResolvedValue({ data: {} });
    api.delete.mockResolvedValue({ data: {} });
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

  it("renders account cards from a nested wrapped accounts response", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        data: {
          accounts: [
            {
              id: 21,
              name: "Savings Goal",
              type: "savings",
              total_income: 100,
              total_expenses: 25,
              balance: 75,
            },
          ],
        },
      },
    });

    renderAccountsPage();

    expect(await screen.findByText("Savings Goal")).toBeInTheDocument();
    expect(screen.queryByText("No accounts found.")).not.toBeInTheDocument();
  });

  it("updates an existing account name and type", async () => {
    const user = userEvent.setup();
    api.get
      .mockResolvedValueOnce({
        data: {
          accounts: [
            {
              id: 12,
              name: "Everyday Chequing",
              type: "chequing",
              total_income: 2500,
              total_expenses: 842.5,
              balance: 1657.5,
            },
          ],
        },
      })
      .mockResolvedValueOnce({
        data: {
          accounts: [
            {
              id: 12,
              name: "Main RBC",
              type: "savings",
              total_income: 2500,
              total_expenses: 842.5,
              balance: 1657.5,
            },
          ],
        },
      });

    renderAccountsPage();

    expect(await screen.findByText("Everyday Chequing")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editNameInput = screen.getByDisplayValue("Everyday Chequing");
    await user.clear(editNameInput);
    await user.type(editNameInput, "Main RBC");
    await user.selectOptions(screen.getByLabelText("Account type"), "savings");
    await user.click(screen.getByRole("button", { name: "Save Account" }));

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith("/accounts/12", {
        name: "Main RBC",
        type: "savings",
      });
    });

    expect(await screen.findByText("Main RBC")).toBeInTheDocument();
    expect(screen.getAllByText("Savings").length).toBeGreaterThan(0);
  });
});

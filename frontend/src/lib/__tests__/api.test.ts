/* Die Schicht zwischen Oberfläche und Backend.
 *
 * Sie ist unauffällig, bis sie etwas verschluckt: ein 403 mit der
 * Begründung „Diese Anlage verlangt einen zweiten Faktor" wäre als
 * „403 Forbidden" nutzlos, und ein 429 ohne die Wartezeit lässt die
 * Oberfläche raten, wann sie es wieder versuchen darf.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api";

function antwort(status: number, body: unknown, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 403 ? "Forbidden" : "",
    headers: { get: (name: string) => headers[name] ?? headers[name.toLowerCase()] ?? null },
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("Fehlerbehandlung", () => {
  it("reicht die Begründung des Backends durch", async () => {
    // "403 Forbidden" sagt niemandem, was zu tun ist - der Text schon.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      antwort(403, { detail: "Diese Anlage verlangt einen zweiten Faktor." })));

    await expect(api.deals.list({})).rejects.toThrow(/zweiten Faktor/);
  });

  it("merkt sich den Status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(antwort(404, {})));
    await api.deals.list({}).catch((err) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    });
    expect.assertions(2);
  });

  it("liest Retry-After bei einer Drosselung", async () => {
    // Ohne diese Zahl gräbt die Oberfläche den Knopf nicht aus und der
    // Benutzer klickt in eine Wand.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      antwort(429, { detail: "Zu viele Anfragen." }, { "Retry-After": "30" })));

    await api.deals.list({}).catch((err) => {
      expect((err as ApiError).retryAfter).toBe(30);
    });
    expect.assertions(1);
  });

  it("kommt ohne Retry-After zurecht", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(antwort(429, {})));
    await api.deals.list({}).catch((err) => {
      expect((err as ApiError).retryAfter).toBeUndefined();
    });
    expect.assertions(1);
  });

  it("überlebt eine Antwort, die kein JSON ist", async () => {
    // Ein Reverse-Proxy, der eine HTML-Fehlerseite liefert, ist der
    // Normalfall - nicht der Ausnahmefall.
    const kaputt = {
      ok: false, status: 502, statusText: "Bad Gateway",
      headers: { get: () => null },
      json: async () => { throw new Error("kein JSON"); },
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(kaputt));

    await expect(api.deals.list({})).rejects.toThrow(/502/);
  });
});

describe("Anfragen", () => {
  it("schickt das Sitzungs-Cookie mit", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(antwort(200, { deals: [] }));
    vi.stubGlobal("fetch", fetchSpy);

    await api.deals.list({});
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("setzt den Content-Type nur, wo ein Rumpf mitgeht", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(antwort(200, {}));
    vi.stubGlobal("fetch", fetchSpy);

    await api.deals.list({});
    expect(fetchSpy.mock.calls[0][1]?.headers).toBeUndefined();

    await api.auth.login("cillian", "geheim");
    expect(fetchSpy.mock.calls[1][1]?.headers)
      .toMatchObject({ "Content-Type": "application/json" });
  });

  it("gibt bei 204 nichts zurück, statt am leeren Rumpf zu scheitern", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 204, headers: { get: () => null },
      json: async () => { throw new Error("leer"); },
    } as unknown as Response));

    await expect(api.auth.logout()).resolves.toBeUndefined();
  });

  it("hängt jede Anfrage unter /api", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(antwort(200, {}));
    vi.stubGlobal("fetch", fetchSpy);
    await api.auth.status();
    expect(fetchSpy.mock.calls[0][0]).toMatch(/^\/api\//);
  });
});

import { describe, expect, it } from "vitest";
import { createGateway, DEMO_DATE } from "./data";

describe("demo gateway", () => {
  it("exposes a score-ready seeded dataset and analytics shape", async () => {
    const gateway = createGateway();
    const login = await gateway.login("admin", "admin123");

    expect(login.user.role).toBe("ADMIN");
    const stats = await gateway.stats();
    expect(stats.total_books).toBeGreaterThanOrEqual(10);
    expect(stats.total_readers).toBeGreaterThanOrEqual(5);
    expect(stats.active_loans).toBe(7);
    expect(stats.overdue_loans).toBe(3);

    const analytics = await gateway.analytics(7);
    expect(analytics.as_of).toBe(DEMO_DATE);
    expect(analytics.daily_trends).toHaveLength(7);
    expect(analytics.daily_trends[0]).toHaveProperty("borrowed");
    expect(analytics.category_distribution.length).toBeGreaterThan(0);
    expect(analytics.overdue_buckets.map((item) => item.label)).toEqual(["1–7 天", "8–30 天", "31 天以上"]);
  });

  it("keeps borrow and return inventory changes atomic in demo mode", async () => {
    const gateway = createGateway();
    await gateway.login("admin", "admin123");
    const before = await gateway.getBook(8);
    const loan = await gateway.borrow({ book_code: before.book_code, reader_id: 8 });
    expect((await gateway.getBook(8)).available_quantity).toBe(before.available_quantity - 1);

    await gateway.returnLoan(loan.id);
    expect((await gateway.getBook(8)).available_quantity).toBe(before.available_quantity);
  });
});

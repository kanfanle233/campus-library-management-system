import type {
  Analytics, AppError, Book, BookPayload, BookQuery, DashboardStats, FileImportResult,
  Gateway, Loan, LoanQuery, LoginResponse, Page, PopularBook, ReaderPayload, ReturnPreview,
  User,
} from "./types";
import { AppError as DomainError } from "./types";
import Papa from "papaparse";

export const DEMO_DATE = "2026-08-31";
const TOKEN_KEY = "library_access_token";
const USER_KEY = "library_user";

const dateShift = (date: string, offset: number) => {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
};

const money = (cents: number) => `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
const normalizeIsbn = (value: string) => value.trim().replace(/[\s-]+/g, "");
const isAdmin = (user: User | null) => user?.role === "ADMIN";

const initialBooks = (): Book[] => {
  const titles = [
    "人工智能导论", "Python 编程基础", "数据结构与算法", "机器学习实战", "计算机网络",
    "数据库系统概论", "深度学习", "软件工程实践", "信息可视化设计", "自然语言处理",
    "计算机组成原理", "操作系统", "概率论与数理统计", "用户体验设计", "数字图书馆",
  ];
  const categories = ["人工智能", "编程", "算法", "数据科学", "计算机基础"];
  return titles.map((title, index) => {
    const total = 1 + (index % 4 === 0 ? 2 : index % 3 === 0 ? 1 : 0);
    return {
      id: index + 1, book_code: `BK${String(index + 1).padStart(6, "0")}`, title,
      author: ["李明", "王芳", "张伟", "陈思", "周宁"][index % 5],
      isbn: `978DEMO${String(index + 1).padStart(6, "0")}`, publisher: "立达大学出版社",
      price: money(2800 + index * 375), category: categories[index % categories.length],
      total_quantity: total, available_quantity: total, is_active: true,
    };
  });
};

const initialReaders = (): User[] => Array.from({ length: 8 }, (_, index) => ({
  id: index + 1, login_name: `DEMO-S${String(index + 1).padStart(3, "0")}`,
  student_id: `DEMO-S${String(index + 1).padStart(3, "0")}`, name: ["林晓", "陈晨", "赵阳", "孙悦", "周航", "吴桐", "郑琳", "徐安"][index],
  contact: `13800000${String(index + 1).padStart(3, "0")}`, borrow_limit: index % 3 === 0 ? 3 : 5,
  role: "READER", is_active: true, created_at: `${dateShift(DEMO_DATE, -120 + index)}T08:00:00Z`, updated_at: `${DEMO_DATE}T08:00:00Z`,
}));

interface DemoState { books: Book[]; readers: User[]; loans: Loan[]; nextBookId: number; nextReaderId: number; nextLoanId: number; actor: User | null; }

const buildDemoState = (): DemoState => {
  const books = initialBooks();
  const readers = initialReaders();
  const admin: User = { id: 100, login_name: "admin", student_id: null, name: "演示管理员", contact: null, borrow_limit: 5, role: "ADMIN", is_active: true, created_at: `${dateShift(DEMO_DATE, -180)}T08:00:00Z`, updated_at: `${DEMO_DATE}T08:00:00Z` };
  const loans: Loan[] = [];
  for (let index = 0; index < 12; index += 1) {
    const reader = readers[index % readers.length];
    const book = books[index];
    const active = index < 7;
    const borrowDate = dateShift(DEMO_DATE, index < 3 ? -(40 + index * 8) : -(5 + index * 4));
    const dueDate = dateShift(borrowDate, 30);
    const returnDate = active ? null : dateShift(DEMO_DATE, -(index - 6));
    const overdue = Math.max(0, Math.floor((new Date(`${(returnDate || DEMO_DATE)}T00:00:00Z`).getTime() - new Date(`${dueDate}T00:00:00Z`).getTime()) / 86400000));
    if (active) book.available_quantity = Math.max(0, book.available_quantity - 1);
    loans.push({ id: index + 1, loan_no: `LN${String(index + 1).padStart(6, "0")}`, reader_id: reader.id, student_id: reader.student_id, reader_name: reader.name, book_id: book.id, book_code: book.book_code, book_title: book.title, isbn: book.isbn, borrow_date: borrowDate, due_date: dueDate, return_date: returnDate, status: active ? "BORROWED" : "RETURNED", overdue_days: overdue, fine_amount: active ? "0.00" : money(overdue * 10), fine_status: active ? "NONE" : overdue > 0 ? "UNPAID" : "NONE" });
  }
  return { books, readers: [...readers, admin], loans, nextBookId: 16, nextReaderId: 9, nextLoanId: 13, actor: null };
};

const clone = <T,>(value: T): T => structuredClone(value);

function assertActor(actor: User | null): User {
  if (!actor || !actor.is_active) throw new DomainError("请先登录", "AUTH_INVALID_CREDENTIALS", 401);
  return actor;
}

function assertAdmin(actor: User | null): User {
  const current = assertActor(actor);
  if (!isAdmin(current)) throw new DomainError("仅管理员可以执行此操作", "FORBIDDEN", 403);
  return current;
}

function page<T>(items: T[], current = 1, size = 20): Page<T> {
  const start = (current - 1) * size;
  return { items: items.slice(start, start + size), total: items.length, page: current, page_size: size };
}

function loanView(state: DemoState, loan: Loan): Loan {
  const book = state.books.find((item) => item.id === loan.book_id);
  const reader = state.readers.find((item) => item.id === loan.reader_id);
  const overdue = Math.max(0, Math.floor((new Date(`${(loan.return_date || DEMO_DATE)}T00:00:00Z`).getTime() - new Date(`${loan.due_date}T00:00:00Z`).getTime()) / 86400000));
  return { ...loan, book_code: book?.book_code || loan.book_code, book_title: book?.title || loan.book_title, reader_name: reader?.name || loan.reader_name, overdue_days: overdue, fine_amount: money(overdue * 10), fine_status: loan.fine_status };
}

class DemoGateway implements Gateway {
  readonly mode = "demo" as const;
  private state = buildDemoState();
  private currentUser: User | null = null;

  private actor() { return this.currentUser; }
  private commit<T>(fn: (draft: DemoState) => T): T {
    const draft = clone(this.state);
    const result = fn(draft);
    this.state = draft;
    return result;
  }

  async login(username: string, password: string): Promise<LoginResponse> {
    const user = this.state.readers.find((item) => item.login_name?.toLowerCase() === username.trim().toLowerCase() && item.is_active);
    const validAdmin = username.trim() === "admin" && password === "admin123";
    const validReader = user && password === "demo123";
    if (!validAdmin && !validReader) throw new DomainError("账号或密码不正确", "AUTH_INVALID_CREDENTIALS", 401);
    const actor = validAdmin ? this.state.readers.find((item) => item.role === "ADMIN")! : user!;
    this.currentUser = clone(actor);
    return { access_token: `demo-${actor.id}`, token_type: "bearer", user: { id: actor.id, role: actor.role, name: actor.name, student_id: actor.student_id } };
  }

  async me() { return clone(assertActor(this.currentUser)); }

  async listBooks(query: BookQuery = {}) {
    const actor = assertActor(this.currentUser);
    const source = isAdmin(actor) ? this.state.books : this.state.books.filter((item) => item.is_active);
    const fields = [query.title, query.author, query.isbn, query.category, query.book_code].filter(Boolean).map((item) => String(item).toLowerCase());
    const result = source.filter((book) => !fields.length || fields.some((needle) => [book.title, book.author, book.isbn, book.category, book.book_code].some((value) => value?.toLowerCase().includes(needle))));
    return clone(page(result, query.page || 1, query.page_size || 20));
  }

  async getBook(id: number) { const actor = assertActor(this.currentUser); const item = this.state.books.find((book) => book.id === id && (book.is_active || isAdmin(actor))); if (!item) throw new DomainError("图书不存在", "BOOK_NOT_FOUND", 404); return clone(item); }

  async createBook(payload: BookPayload) { assertAdmin(this.currentUser); const isbn = normalizeIsbn(payload.isbn); if (this.state.books.some((book) => book.isbn === isbn)) throw new DomainError("ISBN 已存在", "ISBN_ALREADY_EXISTS", 409); return this.commit((draft) => { const id = draft.nextBookId++; const book: Book = { id, book_code: `BK${String(id).padStart(6, "0")}`, ...payload, isbn, price: Number(payload.price || 0).toFixed(2), category: payload.category || "未分类", total_quantity: payload.total_quantity, available_quantity: payload.total_quantity, is_active: true }; draft.books.push(book); return clone(book); }); }

  async updateBook(id: number, payload: Partial<BookPayload>) { assertAdmin(this.currentUser); return this.commit((draft) => { const book = draft.books.find((item) => item.id === id); if (!book) throw new DomainError("图书不存在", "BOOK_NOT_FOUND", 404); const isbn = payload.isbn === undefined ? book.isbn : normalizeIsbn(payload.isbn); if (draft.books.some((item) => item.id !== id && item.isbn === isbn)) throw new DomainError("ISBN 已存在", "ISBN_ALREADY_EXISTS", 409); const borrowed = draft.loans.filter((loan) => loan.book_id === id && loan.status === "BORROWED").length; if (payload.total_quantity !== undefined && payload.total_quantity < borrowed) throw new DomainError("总库存不能少于当前借出数量", "VALIDATION_ERROR", 422); Object.assign(book, payload, { isbn, price: payload.price === undefined ? book.price : Number(payload.price).toFixed(2), available_quantity: payload.total_quantity === undefined ? book.available_quantity : payload.total_quantity - borrowed }); return clone(book); }); }

  async deleteBook(id: number) { assertAdmin(this.currentUser); return this.commit((draft) => { const book = draft.books.find((item) => item.id === id); if (!book) throw new DomainError("图书不存在", "BOOK_NOT_FOUND", 404); const borrowed = draft.loans.filter((loan) => loan.book_id === id && loan.status === "BORROWED").length; if (borrowed) throw new DomainError("图书当前存在借阅记录，不能删除", "BOOK_CURRENTLY_BORROWED", 409, { borrowed_quantity: borrowed }); book.is_active = false; return clone(book); }); }

  async listReaders() { assertAdmin(this.currentUser); return clone(this.state.readers.filter((reader) => reader.role === "READER")); }
  async getReader(id: number) { const actor = assertActor(this.currentUser); if (!isAdmin(actor) && actor.id !== id) throw new DomainError("只能查看自己的资料", "FORBIDDEN", 403); const reader = this.state.readers.find((item) => item.id === id && item.role === "READER"); if (!reader) throw new DomainError("读者不存在", "READER_NOT_FOUND", 404); return clone(reader); }
  async createReader(payload: ReaderPayload) { assertAdmin(this.currentUser); if (this.state.readers.some((item) => item.student_id === payload.student_id)) throw new DomainError("学号已存在", "STUDENT_ID_ALREADY_EXISTS", 409); return this.commit((draft) => { const id = draft.nextReaderId++; const reader: User = { id, login_name: payload.student_id, student_id: payload.student_id, name: payload.name, contact: payload.contact, borrow_limit: payload.borrow_limit, role: "READER", is_active: true, created_at: `${DEMO_DATE}T08:00:00Z`, updated_at: `${DEMO_DATE}T08:00:00Z` }; draft.readers.push(reader); return clone(reader); }); }
  async updateReader(id: number, payload: Partial<ReaderPayload>) { assertAdmin(this.currentUser); return this.commit((draft) => { const reader = draft.readers.find((item) => item.id === id && item.role === "READER"); if (!reader) throw new DomainError("读者不存在", "READER_NOT_FOUND", 404); if (payload.student_id && draft.readers.some((item) => item.id !== id && item.student_id === payload.student_id)) throw new DomainError("学号已存在", "STUDENT_ID_ALREADY_EXISTS", 409); Object.assign(reader, payload, payload.student_id ? { login_name: payload.student_id } : {}); return clone(reader); }); }
  async deleteReader(id: number) { assertAdmin(this.currentUser); return this.commit((draft) => { const reader = draft.readers.find((item) => item.id === id && item.role === "READER"); if (!reader) throw new DomainError("读者不存在", "READER_NOT_FOUND", 404); if (draft.loans.some((loan) => loan.reader_id === id && loan.status === "BORROWED")) throw new DomainError("读者存在未归还借阅，不能注销", "READER_HAS_ACTIVE_LOANS", 409); reader.is_active = false; return clone(reader); }); }

  async listLoans(query: LoanQuery = {}) { const actor = assertActor(this.currentUser); let result = this.state.loans.map((loan) => loanView(this.state, loan)); if (!isAdmin(actor)) result = result.filter((loan) => loan.reader_id === actor.id); const loanNo = query.loan_no?.trim(); const studentId = query.student_id?.trim(); if (loanNo) result = result.filter((loan) => loan.loan_no === loanNo); if (studentId && isAdmin(actor)) result = result.filter((loan) => loan.student_id === studentId); if (query.status) result = result.filter((loan) => loan.status === query.status); if (query.overdue !== undefined) result = result.filter((loan) => query.overdue ? loan.status === "BORROWED" && loan.overdue_days > 0 : loan.status === "RETURNED" || (loan.status === "BORROWED" && loan.overdue_days === 0)); result.sort((a, b) => b.id - a.id); return clone(page(result, query.page || 1, query.page_size || 20)); }
  async getLoan(id: number) { const actor = assertActor(this.currentUser); const loan = this.state.loans.find((item) => item.id === id); if (!loan || (!isAdmin(actor) && loan.reader_id !== actor.id)) throw new DomainError("借阅记录不存在", "LOAN_NOT_FOUND", 404); return clone(loanView(this.state, loan)); }

  async borrow(payload: { book_id?: number; isbn?: string; book_code?: string; reader_id?: number }) { const actor = assertActor(this.currentUser); const identifiers = [payload.book_id !== undefined, payload.isbn !== undefined, payload.book_code !== undefined].filter(Boolean); if (identifiers.length !== 1) throw new DomainError("必须提供一种图书标识", "VALIDATION_ERROR", 422); const readerId = isAdmin(actor) ? payload.reader_id : actor.id; if (!readerId) throw new DomainError("管理员办理借阅时需要选择读者", "VALIDATION_ERROR", 422); return this.commit((draft) => { const reader = draft.readers.find((item) => item.id === readerId && item.role === "READER" && item.is_active); if (!reader) throw new DomainError("读者不存在或已停用", "READER_NOT_FOUND", 404); const book = draft.books.find((item) => item.is_active && (payload.book_id === item.id || (payload.isbn && item.isbn === normalizeIsbn(payload.isbn)) || (payload.book_code && item.book_code === payload.book_code?.trim()))); if (!book) throw new DomainError("图书不存在或已停用", "BOOK_NOT_FOUND", 404); if (book.available_quantity <= 0) throw new DomainError("当前图书没有可借库存", "BOOK_OUT_OF_STOCK", 409); if (draft.loans.filter((loan) => loan.reader_id === readerId && loan.status === "BORROWED").length >= reader.borrow_limit) throw new DomainError("已达到读者借阅上限", "READER_BORROW_LIMIT_REACHED", 409); if (draft.loans.some((loan) => loan.reader_id === readerId && loan.status === "BORROWED" && loan.overdue_days > 0)) throw new DomainError("存在逾期未还图书", "READER_HAS_OVERDUE_LOANS", 409); book.available_quantity -= 1; const id = draft.nextLoanId++; const loan: Loan = { id, loan_no: `LN${String(id).padStart(6, "0")}`, reader_id: readerId, student_id: reader.student_id, reader_name: reader.name, book_id: book.id, book_code: book.book_code, book_title: book.title, isbn: book.isbn, borrow_date: DEMO_DATE, due_date: dateShift(DEMO_DATE, 30), return_date: null, status: "BORROWED", overdue_days: 0, fine_amount: "0.00", fine_status: "NONE" }; draft.loans.push(loan); return clone(loanView(draft, loan)); }); }

  async returnPreview(id: number): Promise<ReturnPreview> { const loan = await this.getLoan(id); if (loan.status === "RETURNED") throw new DomainError("该图书已经归还", "LOAN_ALREADY_RETURNED", 409); return { loan_no: loan.loan_no, book_title: loan.book_title, due_date: loan.due_date, return_date: DEMO_DATE, overdue_days: loan.overdue_days, fine_amount: loan.fine_amount, fine_status: loan.overdue_days > 0 ? "UNPAID" : "NONE" }; }
  async returnLoan(id: number) { const actor = assertActor(this.currentUser); return this.commit((draft) => { const loan = draft.loans.find((item) => item.id === id); if (!loan || (!isAdmin(actor) && loan.reader_id !== actor.id)) throw new DomainError("借阅记录不存在", "LOAN_NOT_FOUND", 404); if (loan.status === "RETURNED") throw new DomainError("该图书已经归还", "LOAN_ALREADY_RETURNED", 409); loan.status = "RETURNED"; loan.return_date = DEMO_DATE; const book = draft.books.find((item) => item.id === loan.book_id); if (book) book.available_quantity = Math.min(book.total_quantity, book.available_quantity + 1); loan.overdue_days = Math.max(0, Math.floor((new Date(`${DEMO_DATE}T00:00:00Z`).getTime() - new Date(`${loan.due_date}T00:00:00Z`).getTime()) / 86400000)); loan.fine_amount = money(loan.overdue_days * 10); loan.fine_status = loan.overdue_days ? "UNPAID" : "NONE"; return clone(loanView(draft, loan)); }); }
  async payFine(id: number) { assertAdmin(this.currentUser); return this.commit((draft) => { const loan = draft.loans.find((item) => item.id === id); if (!loan) throw new DomainError("借阅记录不存在", "LOAN_NOT_FOUND", 404); if (loan.status !== "RETURNED") throw new DomainError("图书归还后才能登记罚款", "FINE_NOT_PAYABLE", 409); loan.fine_status = loan.fine_amount === "0.00" ? "NONE" : "PAID"; return clone(loanView(draft, loan)); }); }

  async stats(): Promise<DashboardStats> { assertActor(this.currentUser); const books = this.state.books.filter((book) => book.is_active); const loans = this.state.loans.map((loan) => loanView(this.state, loan)); const parseCents = (value: string) => { const match = value.match(/^(\d+)(?:\.(\d{1,2}))?$/); return match ? Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0") || 0) : 0; }; return { total_books: books.length, total_copies: books.reduce((sum, book) => sum + book.total_quantity, 0), available_copies: books.reduce((sum, book) => sum + book.available_quantity, 0), total_readers: this.state.readers.filter((reader) => reader.role === "READER" && reader.is_active).length, active_loans: loans.filter((loan) => loan.status === "BORROWED").length, overdue_loans: loans.filter((loan) => loan.status === "BORROWED" && loan.overdue_days > 0).length, unpaid_fines: money(loans.filter((loan) => loan.fine_status === "UNPAID").reduce((sum, loan) => sum + parseCents(loan.fine_amount), 0)) }; }

  async analytics(days: 7 | 30 | 90): Promise<Analytics> { assertAdmin(this.currentUser); const start = dateShift(DEMO_DATE, -(days - 1)); const trends = Array.from({ length: days }, (_, index) => { const date = dateShift(start, index); return { date, borrowed: this.state.loans.filter((loan) => loan.borrow_date === date).length, returned: this.state.loans.filter((loan) => loan.return_date === date).length }; }); const activeBooks = this.state.books.filter((book) => book.is_active); const categoryMap = new Map<string, { title_count: number; copy_count: number }>(); activeBooks.forEach((book) => { const key = book.category || "未分类"; const value = categoryMap.get(key) || { title_count: 0, copy_count: 0 }; value.title_count += 1; value.copy_count += book.total_quantity; categoryMap.set(key, value); }); const popular: PopularBook[] = [...new Map(this.state.loans.filter((loan) => loan.borrow_date >= start).map((loan) => [loan.book_id, loan])).values()].map((loan) => ({ book_id: loan.book_id, book_code: loan.book_code, title: loan.book_title, borrow_count: this.state.loans.filter((item) => item.book_id === loan.book_id && item.borrow_date >= start).length })).sort((a, b) => b.borrow_count - a.borrow_count || a.book_id - b.book_id).slice(0, 5); const overdue = this.state.loans.map((loan) => loanView(this.state, loan)).filter((loan) => loan.status === "BORROWED" && loan.overdue_days > 0); return { as_of: DEMO_DATE, start_date: start, end_date: DEMO_DATE, daily_trends: trends, category_distribution: [...categoryMap.entries()].map(([category, values]) => ({ category, ...values })).sort((a, b) => b.copy_count - a.copy_count), popular_books: popular, overdue_buckets: [{ label: "1–7 天", count: overdue.filter((loan) => loan.overdue_days <= 7).length }, { label: "8–30 天", count: overdue.filter((loan) => loan.overdue_days >= 8 && loan.overdue_days <= 30).length }, { label: "31 天以上", count: overdue.filter((loan) => loan.overdue_days >= 31).length }] }; }

  async importBooks(file: File): Promise<FileImportResult> { assertAdmin(this.currentUser); const text = await file.text(); const parsed = Papa.parse<string[]>(text, { skipEmptyLines: "greedy" }); const rows = parsed.data; if (!rows.length) throw new DomainError("CSV 文件不能为空", "VALIDATION_ERROR", 422); const header = rows[0].map((value) => value.replace(/^\uFEFF/, "").trim()).join(","); const expected = "title,author,isbn,publisher,price,total_quantity,category"; const expectedAlias = "title,author,isbn,publisher,price,quantity,category"; if (header !== expected && header !== expectedAlias) return { total: 0, success: 0, failed: 1, errors: [{ row: 1, reason: "表头必须为课程规定列" }] }; const bodyRows = rows.slice(1).map((values, index) => ({ row: index + 2, values })); const errors = [...parsed.errors.map((item) => ({ row: (item.row || 0) + 1, reason: item.message })), ...bodyRows.filter((row) => row.values.length !== 7).map((row) => ({ row: row.row, reason: "列数与表头不一致" }))]; if (errors.length) return { total: bodyRows.length, success: 0, failed: errors.length, errors }; const payloads = bodyRows.map((row) => { const [title, author, isbn, publisher, price, quantity, category] = row.values; return { row: row.row, payload: { title: title.trim(), author: author.trim(), isbn: isbn.trim(), publisher: publisher.trim(), price: price.trim(), total_quantity: Number(quantity), category: category.trim() } as BookPayload }; }); const duplicates = new Set<string>(); const validation = payloads.filter((row) => { const normalized = normalizeIsbn(row.payload.isbn); const price = Number(row.payload.price); const invalid = !row.payload.title || !row.payload.author || !normalized || !Number.isFinite(price) || price < 0 || !Number.isInteger(row.payload.total_quantity) || row.payload.total_quantity < 0 || duplicates.has(normalized) || this.state.books.some((book) => book.isbn === normalized); duplicates.add(normalized); return invalid; }).map((row) => ({ row: row.row, reason: "必填字段、价格、数量或 ISBN 不合法/重复" })); if (validation.length) return { total: bodyRows.length, success: 0, failed: validation.length, errors: validation }; return this.commit((draft) => { payloads.forEach(({ payload }) => { const id = draft.nextBookId++; draft.books.push({ id, book_code: `BK${String(id).padStart(6, "0")}`, ...payload, isbn: normalizeIsbn(payload.isbn), price: Number(payload.price || 0).toFixed(2), category: payload.category || "未分类", available_quantity: payload.total_quantity, is_active: true }); }); return { total: bodyRows.length, success: bodyRows.length, failed: 0, errors: [] }; }); }

  async exportCsv(kind: "books" | "readers" | "loans") { assertAdmin(this.currentUser); const rows = kind === "books" ? [["book_code", "title", "author", "isbn", "publisher", "price", "total_quantity", "available_quantity", "category", "is_active"], ...this.state.books.map((book) => [book.book_code, book.title, book.author, book.isbn, book.publisher || "", book.price, book.total_quantity, book.available_quantity, book.category || "", String(book.is_active)])] : kind === "readers" ? [["id", "login_name", "student_id", "name", "contact", "borrow_limit", "role", "is_active"], ...this.state.readers.filter((reader) => reader.role === "READER").map((reader) => [reader.id, reader.login_name || "", reader.student_id || "", reader.name, reader.contact || "", reader.borrow_limit, reader.role, String(reader.is_active)])] : [["loan_no", "student_id", "book_code", "borrow_date", "due_date", "return_date", "overdue_days", "fine_amount", "status", "fine_status"], ...this.state.loans.map((loan) => { const item = loanView(this.state, loan); return [item.loan_no, item.student_id || "", item.book_code, item.borrow_date, item.due_date, item.return_date || "", item.overdue_days, item.fine_amount, item.status, item.fine_status]; })]; const content = "\uFEFF" + rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n"); return new Blob([content], { type: "text/csv;charset=utf-8" }); }
}

class HttpGateway implements Gateway {
  readonly mode = "live" as const;
  private token = sessionStorage.getItem(TOKEN_KEY);
  private base = import.meta.env.VITE_API_BASE || "/api/v1";
  private async request<T>(path: string, init: RequestInit = {}): Promise<T> { const headers = new Headers(init.headers); if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json"); if (this.token) headers.set("Authorization", `Bearer ${this.token}`); const response = await fetch(`${this.base}${path}`, { ...init, headers }); let body: unknown = null; const type = response.headers.get("content-type") || ""; if (type.includes("json")) body = await response.json(); else if (response.status !== 204) body = await response.text(); if (!response.ok) { const detail = (body as { detail?: { code?: string; message?: string; [key: string]: unknown } } | null)?.detail; if (response.status === 401) { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(USER_KEY); this.token = null; } throw new DomainError(detail?.message || "请求失败，请稍后重试", detail?.code || `HTTP_${response.status}`, response.status, detail); } return body as T; }
  async login(username: string, password: string) { const response = await this.request<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }); this.token = response.access_token; sessionStorage.setItem(TOKEN_KEY, this.token); sessionStorage.setItem(USER_KEY, JSON.stringify(response.user)); return response; }
  me() { return this.request<User>("/auth/me"); }
  listBooks(query: BookQuery = {}) { const params = new URLSearchParams(); Object.entries(query).forEach(([key, value]) => value !== undefined && value !== "" && params.set(key, String(value))); return this.request<Page<Book>>(`/books?${params}`); }
  getBook(id: number) { return this.request<Book>(`/books/${id}`); }
  createBook(payload: BookPayload) { return this.request<Book>("/books", { method: "POST", body: JSON.stringify(payload) }); }
  updateBook(id: number, payload: Partial<BookPayload>) { return this.request<Book>(`/books/${id}`, { method: "PATCH", body: JSON.stringify(payload) }); }
  deleteBook(id: number) { return this.request<Book>(`/books/${id}`, { method: "DELETE" }); }
  listReaders() { return this.request<User[]>("/readers"); }
  getReader(id: number) { return this.request<User>(`/readers/${id}`); }
  createReader(payload: ReaderPayload) { return this.request<User>("/readers", { method: "POST", body: JSON.stringify(payload) }); }
  updateReader(id: number, payload: Partial<ReaderPayload>) { return this.request<User>(`/readers/${id}`, { method: "PATCH", body: JSON.stringify(payload) }); }
  deleteReader(id: number) { return this.request<User>(`/readers/${id}`, { method: "DELETE" }); }
  listLoans(query: LoanQuery = {}) { const params = new URLSearchParams(); Object.entries(query).forEach(([key, value]) => value !== undefined && value !== "" && params.set(key, String(value))); return this.request<Page<Loan>>(`/loans?${params}`); }
  borrow(payload: { book_id?: number; isbn?: string; book_code?: string; reader_id?: number }) { return this.request<Loan>("/loans/borrow", { method: "POST", body: JSON.stringify(payload) }); }
  getLoan(id: number) { return this.request<Loan>(`/loans/${id}`); }
  returnPreview(id: number) { return this.request<ReturnPreview>(`/loans/${id}/return-preview`); }
  returnLoan(id: number) { return this.request<Loan>(`/loans/${id}/return`, { method: "POST" }); }
  payFine(id: number) { return this.request<Loan>(`/loans/${id}/fine/pay`, { method: "POST" }); }
  stats() { return this.request<DashboardStats>("/dashboard/stats"); }
  analytics(days: 7 | 30 | 90) { return this.request<Analytics>(`/dashboard/analytics?days=${days}`); }
  async importBooks(file: File) { const form = new FormData(); form.append("file", file); return this.request<FileImportResult>("/files/books/import", { method: "POST", body: form }); }
  exportCsv(kind: "books" | "readers" | "loans") { return fetch(`${this.base}/files/${kind}/export`, { headers: this.token ? { Authorization: `Bearer ${this.token}` } : {} }).then(async (response) => { if (!response.ok) throw new DomainError("导出失败", `HTTP_${response.status}`, response.status); return response.blob(); }); }
}

export const clearSession = () => { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(USER_KEY); };
export const storedUser = (): User | null => { try { const value = sessionStorage.getItem(USER_KEY); return value ? JSON.parse(value) as User : null; } catch { return null; } };
export const createGateway = (): Gateway => import.meta.env.VITE_DATA_MODE === "live" ? new HttpGateway() : new DemoGateway();

export type UserRole = "ADMIN" | "READER";
export type LoanStatus = "BORROWED" | "RETURNED";
export type FineStatus = "NONE" | "UNPAID" | "PAID";

export interface User {
  id: number;
  login_name: string | null;
  student_id: string | null;
  name: string;
  contact: string | null;
  borrow_limit: number;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginIdentity {
  id: number;
  role: UserRole;
  name: string;
  student_id: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: LoginIdentity;
}

export interface Book {
  id: number;
  book_code: string;
  title: string;
  author: string;
  isbn: string;
  publisher: string | null;
  price: string;
  category: string | null;
  total_quantity: number;
  available_quantity: number;
  is_active: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Loan {
  id: number;
  loan_no: string;
  reader_id: number;
  student_id: string | null;
  reader_name: string;
  book_id: number;
  book_code: string;
  book_title: string;
  isbn: string;
  borrow_date: string;
  due_date: string;
  return_date: string | null;
  status: LoanStatus;
  overdue_days: number;
  fine_amount: string;
  fine_status: FineStatus;
}

export interface ReturnPreview {
  loan_no: string;
  book_title: string;
  due_date: string;
  return_date: string;
  overdue_days: number;
  fine_amount: string;
  fine_status: FineStatus;
}

export interface DashboardStats {
  total_books: number;
  total_copies: number;
  available_copies: number;
  total_readers: number;
  active_loans: number;
  overdue_loans: number;
  unpaid_fines: string;
}

export interface DailyTrend {
  date: string;
  borrowed: number;
  returned: number;
}

export interface CategoryStat {
  category: string;
  title_count: number;
  copy_count: number;
}

export interface PopularBook {
  book_id: number;
  book_code: string;
  title: string;
  borrow_count: number;
}

export interface OverdueBucket {
  label: string;
  count: number;
}

export interface Analytics {
  as_of: string;
  start_date: string;
  end_date: string;
  daily_trends: DailyTrend[];
  category_distribution: CategoryStat[];
  popular_books: PopularBook[];
  overdue_buckets: OverdueBucket[];
}

export interface FileImportError {
  row: number;
  reason: string;
}

export interface FileImportResult {
  total: number;
  success: number;
  failed: number;
  errors: FileImportError[];
}

export interface BookPayload {
  title: string;
  author: string;
  isbn: string;
  publisher: string;
  price: string;
  category: string;
  total_quantity: number;
}

export interface ReaderPayload {
  name: string;
  student_id: string;
  contact: string;
  borrow_limit: number;
  password?: string;
}

export interface BookQuery {
  title?: string;
  author?: string;
  isbn?: string;
  category?: string;
  book_code?: string;
  page?: number;
  page_size?: number;
}

export interface LoanQuery {
  loan_no?: string;
  student_id?: string;
  status?: LoanStatus;
  overdue?: boolean;
  page?: number;
  page_size?: number;
}

export interface Gateway {
  readonly mode: "demo" | "live";
  login(username: string, password: string): Promise<LoginResponse>;
  me(): Promise<User>;
  listBooks(query?: BookQuery): Promise<Page<Book>>;
  getBook(id: number): Promise<Book>;
  createBook(payload: BookPayload): Promise<Book>;
  updateBook(id: number, payload: Partial<BookPayload>): Promise<Book>;
  deleteBook(id: number): Promise<Book>;
  listReaders(): Promise<User[]>;
  getReader(id: number): Promise<User>;
  createReader(payload: ReaderPayload): Promise<User>;
  updateReader(id: number, payload: Partial<ReaderPayload>): Promise<User>;
  deleteReader(id: number): Promise<User>;
  listLoans(query?: LoanQuery): Promise<Page<Loan>>;
  borrow(payload: { book_id?: number; isbn?: string; book_code?: string; reader_id?: number }): Promise<Loan>;
  getLoan(id: number): Promise<Loan>;
  returnPreview(id: number): Promise<ReturnPreview>;
  returnLoan(id: number): Promise<Loan>;
  payFine(id: number): Promise<Loan>;
  stats(): Promise<DashboardStats>;
  analytics(days: 7 | 30 | 90): Promise<Analytics>;
  importBooks(file: File): Promise<FileImportResult>;
  exportCsv(kind: "books" | "readers" | "loans"): Promise<Blob>;
}

export class AppError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(message: string, code = "UNKNOWN_ERROR", status = 400, details?: Record<string, unknown>) {
    super(message);
    this.name = "AppError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

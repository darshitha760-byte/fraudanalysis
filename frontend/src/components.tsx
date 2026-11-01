import type { ReactNode } from "react";
import { AlertCircle, ArrowDownToLine, Inbox, LoaderCircle, RefreshCw } from "lucide-react";

export function Status({ loading, error, retry }: { loading: boolean; error: string; retry: () => void }) {
  if (loading) return <div className="state" role="status"><LoaderCircle className="spin" size={24} /><span>Loading your workspace...</span></div>;
  if (error) return <div className="notice error" role="alert"><AlertCircle size={19} /><span>{error}</span><button onClick={retry} className="button secondary"><RefreshCw size={15} />Retry</button></div>;
  return null;
}
export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`notice ${error ? "error" : ""}`} role={error ? "alert" : "status"}><AlertCircle size={18} /><div>{children}</div></div>;
}
export function Badge({ value }: { value: string | null | undefined }) {
  const text = value || "unassessed";
  return <span className={`badge ${text.toLowerCase().replaceAll(" ", "-")}`}>{text.replaceAll("_", " ")}</span>;
}
export function Metric({ title, value, note, icon }: { title: string; value: ReactNode; note: string; icon: ReactNode }) {
  return <div className="metric card"><div className="metric-top"><span>{title}</span><div className="metric-icon">{icon}</div></div><strong>{value}</strong><small>{note}</small></div>;
}
export function Heading({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div><div className="heading-actions">{children}</div></div>;
}
export function Panel({ title, description, children, action }: { title: string; description?: string; children: ReactNode; action?: ReactNode }) {
  return <section className="card panel"><header className="panel-heading"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</header>{children}</section>;
}
export function DataTable<T>({ rows, columns, rowKey, empty = "No records match your filters." }: {
  rows: T[]; rowKey: (row: T) => string | number;
  columns: { title: string; cell: (row: T) => ReactNode }[]; empty?: string;
}) {
  if (!rows.length) return <div className="state"><Inbox size={30} /><strong>{empty}</strong><span>Records will appear here when available.</span></div>;
  return <div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column.title}>{column.title}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={rowKey(row)}>{columns.map((column) => <td key={column.title}>{column.cell(row)}</td>)}</tr>)}</tbody></table></div>;
}
export function Pagination({ page, total, limit = 20, onChange }: { page: number; total: number; limit?: number; onChange: (page: number) => void }) {
  return <div className="pagination"><span>{total.toLocaleString()} records <span className="muted">/ Page {page} of {Math.max(1, Math.ceil(total / limit))}</span></span><div><button className="button secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button><button className="button secondary" disabled={page * limit >= total} onClick={() => onChange(page + 1)}>Next</button></div></div>;
}
export function ExportButton({ rows, filename }: { rows: Record<string, string | number | null>[]; filename: string }) {
  function download() {
    const keys = Object.keys(rows[0] || {});
    const escape = (value: unknown) => {
      const text = String(value ?? "");
      return `"${(/^[=+\-@\t\r]/.test(text) ? "'" : "") + text.replaceAll('"', '""')}"`;
    };
    const csv = [keys, ...rows.map((row) => keys.map((key) => row[key]))].map((row) => row.map(escape).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${filename}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return <button className="button secondary" disabled={!rows.length} onClick={download}><ArrowDownToLine size={16} />Export current page</button>;
}

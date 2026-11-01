import { useState, type FormEvent } from "react";
import { Search, X } from "lucide-react";
import { count, dateTime, money, useResource } from "../api";
import { Badge, DataTable, ExportButton, Heading, Pagination, Panel, Status } from "../components";
import type { Paginated, Transaction } from "../types";

export function TransactionsPage() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState("");
  const [selected, setSelected] = useState<number>();
  const resource = useResource<Paginated<Transaction>>(`/api/transactions?page=${page}&limit=20${filters}`);
  const detail = useResource<Record<string, unknown>>(selected ? `/api/transactions/${selected}` : null);
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const entries = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    entries.forEach((value, key) => { if (String(value).trim()) params.set(key, String(value).trim()); });
    if (params.has("end_date")) params.set("end_date", `${params.get("end_date")}T23:59:59.999999`);
    setFilters(params.size ? `&${params}` : "");
    setPage(1);
  }
  return <>
    <Heading eyebrow="FOLLOW THE MONEY" title="Transaction explorer" description="Search your transaction ledger and inspect the risk behind each payment."><ExportButton rows={(resource.data?.data || []).map((row) => ({ ...row }))} filename="transactions" /></Heading>
    <Panel title="Transaction ledger" description={resource.data ? `${count(resource.data.pagination.total)} matching transactions` : "Filter and explore your transaction history"}>
      <form className="filter-bar" onSubmit={search}><label className="search-input"><Search size={17} /><input name="transaction_id" placeholder="Search transaction ID..." aria-label="Transaction ID" /></label><label>Customer ID<input name="customer_id" type="number" min="1" placeholder="All customers" /></label><label>Risk level<select name="risk_level"><option value="">All risk levels</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><label>From<input type="date" name="start_date" /></label><label>To<input type="date" name="end_date" /></label><button className="button primary">Apply filters</button></form>
      <Status {...resource} retry={resource.refresh} />
      {resource.data && <><DataTable rows={resource.data.data} rowKey={(row) => row.id} columns={[
        { title: "Transaction", cell: (row) => <button className="text-button mono" onClick={() => setSelected(row.id)}>{row.transaction_id}</button> },
        { title: "Merchant", cell: (row) => <div className="cell-stack"><strong>{row.merchant_name || "Not recorded"}</strong><small>Customer #{row.customer_id}</small></div> },
        { title: "Amount", cell: (row) => <strong>{money(row.amount, row.currency)}</strong> },
        { title: "Date & time", cell: (row) => dateTime(row.transaction_date) },
        { title: "Risk", cell: (row) => <Badge value={row.risk_level} /> },
        { title: "Score", cell: (row) => row.risk_score == null ? <span className="muted">Unassessed</span> : <span className="risk-score"><i style={{ width: `${Math.max(0, Math.min(100, row.risk_score))}%` }} />{row.risk_score.toFixed(0)}</span> },
        { title: "Status", cell: (row) => <Badge value={row.status} /> },
      ]} /><Pagination page={page} total={resource.data.pagination.total} onChange={setPage} /></>}
    </Panel>
    {selected && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="transaction-title" className="modal"><header><div><div className="eyebrow">TRANSACTION DETAILS</div><h2 id="transaction-title">Transaction #{selected}</h2></div><button className="icon-button" aria-label="Close transaction" onClick={() => setSelected(undefined)}><X /></button></header><Status {...detail} retry={detail.refresh} />{detail.data && <pre className="json-details">{JSON.stringify(detail.data, null, 2)}</pre>}<button className="button secondary" onClick={() => setSelected(undefined)}>Close details</button></section></div>}
  </>;
}

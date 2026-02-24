# Frontend Analysis for Backend Integration

Analysis of **dashboard.html**, **employees.html**, and **leave-requests.html** so you can connect a backend (API) later.  
*(Note: The leave requests page is `leave-requests.html`, not leave-request.html.)*

---

## 1. Shared structure (all three pages)

- **Layout**: Fixed sidebar (280px) + main content area.
- **Navigation**: Links to `dashboard.html`, `employees.html`, `leave-requests.html`.
- **Sidebar footer**: User card with initials "AD", name "Admin User", role "Administrator" (currently static).
- **Styling**: Same CSS variables (primary, success, warning, danger, etc.) and fonts (Sora, DM Sans).
- **No auth checks**: Pages do not verify login; add session/token checks when you add a backend.

---

## 2. dashboard.html

### Purpose
Overview: stats, employee list, and department chart.

### Data the page expects (for backend)

| Data | Element IDs | Expected shape / usage |
|------|-------------|-------------------------|
| **Stats** | `#totalEmployees`, `#activeEmployees`, `#onLeave`, `#lateEmployees` | Four numbers: total, active, on leave, late returns |
| **Employee list** | `#employeeListContainer` | Array of employees (see below) |
| **Chart** | `#employeeChart` (Chart.js) | Labels = department names, data = count per department |

### Employee object (dashboard list)

```javascript
{
  name: string,      // e.g. "John Doe"
  id: string,        // e.g. "EMP001"
  department: string, // e.g. "Engineering"
  status: string     // "active" | "pending" | "approved"
}
```

### JavaScript entry points to replace with API

| Current behavior | Replace with |
|------------------|--------------|
| `stats` object (total, active, onLeave, late) | GET API e.g. `/api/dashboard/stats` |
| `employees` array | GET API e.g. `/api/employees` or `/api/dashboard/employees` |
| Chart `labels` and `data` | GET API e.g. `/api/dashboard/departments` or derive from employees |
| `filterEmployees(filter)` | Can stay client-side (filter API response by `status`) |

### Suggested backend endpoints (dashboard)

- `GET /api/dashboard/stats` → `{ total, active, onLeave, late }`
- `GET /api/employees` (or `/api/dashboard/employees`) → `[{ id, name, department, status }, ...]`
- `GET /api/dashboard/departments` → `[{ name, count }, ...]` for chart (or compute from employees)

---

## 3. employees.html

### Purpose
Employee management: search, add, edit, delete.

### Form fields and IDs

| Action | Input IDs | Purpose |
|--------|-----------|---------|
| **Search** | `#searchId` | Employee ID (e.g. EMP001) |
| **Add** | `#addName`, `#addEmail`, `#addDepartment` | Name, email, department |
| **Edit** | `#editId`, `#editName`, `#editEmail` | Employee ID + new name, new email |
| **Delete** | `#deleteId` | Employee ID to delete |

### Result / message elements

- `#searchResult` – card shown when search succeeds; content goes in `#employeeDetails`.
- `#addMessage`, `#editMessage`, `#deleteMessage` – success/error messages.

### Employee object (search result / backend)

```javascript
{
  id: string,        // e.g. "EMP001"
  name: string,
  email: string,
  department: string,
  position: string   // optional; UI shows it in search result
}
```

### JavaScript functions to wire to backend

| Function | Current behavior | Backend replacement |
|----------|------------------|---------------------|
| `searchEmployee()` | Reads `employees[id]`, fills `#employeeDetails` | GET `/api/employees/:id` (or `?id=EMP001`), then render same HTML |
| `addEmployee()` | Adds to local `employees`, shows message | POST `/api/employees` with `{ name, email, department }`, show success/error in `#addMessage` |
| `editEmployee()` | Updates `employees[id]` (name, email) | PUT/PATCH `/api/employees/:id` with `{ name?, email? }`, show in `#editMessage` |
| `deleteEmployee()` | `delete employees[id]` after confirm | DELETE `/api/employees/:id`, show in `#deleteMessage` |

### Suggested backend endpoints (employees)

- `GET /api/employees/:id` → single employee `{ id, name, email, department, position? }`
- `GET /api/employees` → list (for dashboard/search if needed)
- `POST /api/employees` → body `{ name, email, department }` → create, return employee (e.g. with generated `id`)
- `PUT /api/employees/:id` or `PATCH /api/employees/:id` → body `{ name?, email?, department? }` → update
- `DELETE /api/employees/:id` → delete employee

---

## 4. leave-requests.html

### Purpose
List leave requests, filter by status, approve/reject (per card or by employee ID).

### Form fields and IDs

| Area | Input IDs | Purpose |
|------|-----------|---------|
| Quick action | `#quickActionId` | Employee ID for approve/reject by ID |
| Message | `#quickActionMessage` | Success/error for quick action |

### Leave request object (for backend)

```javascript
{
  id: string,           // employee id e.g. "EMP001" (or a requestId if you prefer)
  name: string,
  department: string,
  startDate: string,    // "YYYY-MM-DD"
  endDate: string,
  days: number,
  returnDate: string,
  reason: string,
  status: string       // "pending" | "approved" | "rejected"
}
```

For a proper backend you may want a separate **request id** (e.g. `requestId`) and keep `id` as employee id; the UI currently uses employee id to find the request.

### JavaScript functions to wire to backend

| Function | Current behavior | Backend replacement |
|----------|------------------|---------------------|
| `renderRequests()` | Renders `leaveRequests` into `#requestsGrid` | GET `/api/leave-requests` (or with `?status=pending`), then render same HTML |
| `filterRequests(status)` | Filters in-memory array, then `renderRequests()` | Option A: same GET, filter client-side. Option B: GET `/api/leave-requests?status=pending` etc. |
| `approveRequest(id)` | Sets `request.status = 'approved'`, re-renders | PATCH `/api/leave-requests/:id` or `/api/leave-requests/:requestId` with `{ status: 'approved' }` |
| `rejectRequest(id)` | Same with `'rejected'` | PATCH with `{ status: 'rejected' }` |
| `approveById()` | Finds request by employee id, approves | Same PATCH; backend can resolve by employee id if you design it that way |
| `rejectById()` | Same for reject | Same as above |

### Suggested backend endpoints (leave requests)

- `GET /api/leave-requests` → `[{ id, name, department, startDate, endDate, days, returnDate, reason, status }, ...]`  
  Optional query: `?status=pending|approved|rejected`
- `PATCH /api/leave-requests/:id` (or `:requestId`) → body `{ status: 'approved' | 'rejected' }`
- Optional: `POST /api/leave-requests` if employees submit from another page (e.g. employee-apply.html).

---

## 5. Summary: API contract checklist

Use this when building your backend:

| Page | GET | POST | PATCH/PUT | DELETE |
|------|-----|------|-----------|--------|
| **Dashboard** | `/api/dashboard/stats`, `/api/employees`, `/api/dashboard/departments` | — | — | — |
| **Employees** | `/api/employees`, `/api/employees/:id` | `/api/employees` | `/api/employees/:id` | `/api/employees/:id` |
| **Leave requests** | `/api/leave-requests` | (optional) | `/api/leave-requests/:id` | — |

---

## 6. Integration steps (high level)

1. **Base URL**: Define a config, e.g. `const API_BASE = 'https://your-api.com/api';` (or relative `/api` if same origin).
2. **Replace hardcoded data**: In each page, replace the inline `stats`, `employees`, `leaveRequests` with `fetch(API_BASE + '/...')` (or axios) and use the response to fill the same DOM elements.
3. **Forms**: In `addEmployee`, `editEmployee`, `deleteEmployee`, `approveRequest`, `rejectRequest`, `approveById`, `rejectById`, send the same payloads to the endpoints above and then refresh data or update the UI from the response.
4. **Errors**: Replace `alert()` and inline messages with your API error handling (e.g. show message in existing `#...Message` divs or toasts).
5. **Auth**: Add auth (e.g. Bearer token or session cookie) to all requests and protect routes; optionally load "Admin User" from a `/me` or user endpoint.
6. **IDs**: Decide if leave request uses **employee id** only or a separate **request id**; adjust PATCH and GET responses accordingly.

---

## 7. File reference

| File | Role |
|------|------|
| `dashboard.html` | Stats, employee list, department chart |
| `employees.html` | Search, add, edit, delete employees |
| `leave-requests.html` | List leave requests, filter, approve/reject by card or by employee ID |

This document and the IDs/functions above are enough to connect your frontend to a backend without changing the existing HTML structure or CSS.

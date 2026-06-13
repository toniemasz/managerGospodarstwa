class PaginationTable {
    constructor(config) {
        this.rows = Array.from(document.querySelectorAll(config.rowSelector));
        this.searchInput = config.searchInputId ? document.getElementById(config.searchInputId) : null;
        this.filterSelect = config.filterSelectId ? document.getElementById(config.filterSelectId) : null;
        this.limitSelect = config.limitSelectId ? document.getElementById(config.limitSelectId) : null;
        this.paginationContainer = document.getElementById(config.paginationContainerId);

        this.currentPage = 1;
        this.limit = this.limitSelect ? parseInt(this.limitSelect.value) : 10;
        this.filteredRows = [...this.rows];

        this.initEvents();
        this.updateTable();
    }

    initEvents() {
        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => this.filterData());
        }
        if (this.filterSelect) {
            this.filterSelect.addEventListener('change', () => this.filterData());
        }
        if (this.limitSelect) {
            this.limitSelect.addEventListener('change', (e) => {
                this.limit = parseInt(e.target.value);
                this.currentPage = 1;
                this.filterData();
            });
        }
    }

    filterData() {
        const query = this.searchInput ? this.searchInput.value.toLowerCase() : '';
        const filterValue = this.filterSelect ? this.filterSelect.value : 'ALL';

        this.filteredRows = this.rows.filter(row => {
            const searchData = (row.dataset.search || '').toLowerCase();
            const filterData = row.dataset.filter || 'ALL';

            const matchesSearch = searchData.includes(query);
            const matchesFilter = filterValue === 'ALL' || filterData === filterValue;

            return matchesSearch && matchesFilter;
        });

        this.currentPage = 1;
        this.updateTable();
    }

    updateTable() {
        this.rows.forEach(row => row.style.display = 'none');

        const start = (this.currentPage - 1) * this.limit;
        const end = start + this.limit;
        const rowsToShow = this.filteredRows.slice(start, end);

        rowsToShow.forEach(row => row.style.display = '');

        this.renderPagination();
    }

    renderPagination() {
        if (!this.paginationContainer) return;

        this.paginationContainer.innerHTML = '';
        this.paginationContainer.className = 'p-4 flex flex-col sm:flex-row justify-between items-center gap-3 border-t bg-slate-50';

        const totalRows = this.filteredRows.length;
        const totalPages = Math.ceil(totalRows / this.limit);
        const start = totalRows === 0 ? 0 : (this.currentPage - 1) * this.limit + 1;
        const end = Math.min(this.currentPage * this.limit, totalRows);

        const summary = document.createElement('span');
        summary.className = 'pagination-summary';
        summary.innerText = `Pokazano ${start}-${end} z ${totalRows}`;
        this.paginationContainer.appendChild(summary);

        if (totalPages <= 1) return;

        const buttons = document.createElement('div');
        buttons.className = 'flex flex-wrap justify-center gap-1.5';

        const createButton = (label, disabled, onClick, isActive = false) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.innerText = label;
            btn.disabled = disabled;
            btn.className = `min-w-9 px-3 py-1.5 rounded-lg border text-sm font-bold transition ${
                isActive
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                    : disabled
                        ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                        : 'bg-white text-gray-700 hover:bg-indigo-50 hover:text-indigo-700 border-gray-300'
            }`;
            btn.onclick = onClick;
            return btn;
        };

        buttons.appendChild(createButton('‹', this.currentPage === 1, () => {
            this.currentPage -= 1;
            this.updateTable();
        }));

        for (let i = 1; i <= totalPages; i++) {
            buttons.appendChild(createButton(String(i), false, () => {
                this.currentPage = i;
                this.updateTable();
            }, i === this.currentPage));
        }

        buttons.appendChild(createButton('›', this.currentPage === totalPages, () => {
            this.currentPage += 1;
            this.updateTable();
        }));

        this.paginationContainer.appendChild(buttons);
    }
}

function enhanceDataTable(table) {
    if (table.dataset.enhanced === 'true') {
        return;
    }

    table.dataset.enhanced = 'true';
    table.classList.add('app-table');

    const parent = table.parentElement;
    const alreadyWrapped = parent && (
        parent.classList.contains('data-table-scroll') ||
        parent.classList.contains('overflow-x-auto')
    );

    if (!alreadyWrapped && table.parentNode) {
        const wrapper = document.createElement('div');
        wrapper.className = 'data-table-scroll';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
    }

    const shell = table.closest('.bg-white, .table-card');
    if (shell) {
        shell.classList.add('table-card');
    }

    const headers = Array.from(table.querySelectorAll('thead th')).map((header) => header.textContent.trim());
    table.querySelectorAll('tbody tr').forEach((row) => {
        Array.from(row.children).forEach((cell, index) => {
            if (headers[index] && !cell.dataset.label) {
                cell.dataset.label = headers[index];
            }
        });
    });
}

function enhanceDataTables() {
    document.querySelectorAll('table').forEach(enhanceDataTable);
}

document.addEventListener('DOMContentLoaded', () => {
    enhanceDataTables();
});

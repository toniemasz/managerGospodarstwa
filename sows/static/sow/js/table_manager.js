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
        // Ukryj wszystkie wiersze
        this.rows.forEach(row => row.style.display = 'none');

        // Oblicz indeksy dla stron
        const start = (this.currentPage - 1) * this.limit;
        const end = start + this.limit;
        const rowsToShow = this.filteredRows.slice(start, end);

        // Pokaż tylko te z bieżącej strony
        rowsToShow.forEach(row => row.style.display = '');

        this.renderPagination();
    }

    renderPagination() {
        if (!this.paginationContainer) return;
        this.paginationContainer.innerHTML = '';

        const totalPages = Math.ceil(this.filteredRows.length / this.limit);
        if (totalPages <= 1) return;

        for (let i = 1; i <= totalPages; i++) {
            const btn = document.createElement('button');
            btn.innerText = i;
            btn.className = `px-3 py-1 border rounded mx-1 text-sm font-medium transition-colors ${
                i === this.currentPage
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow'
                    : 'bg-white text-gray-700 hover:bg-gray-100 border-gray-300'
            }`;
            btn.onclick = () => {
                this.currentPage = i;
                this.updateTable();
            };
            this.paginationContainer.appendChild(btn);
        }
    }
}
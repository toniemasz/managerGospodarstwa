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

// Funkcje do edycji maciory
function toggleEditMode() {
    const earInput = document.getElementById('ear_tag_input');
    const dateInput = document.getElementById('entry_date_input');

    [earInput, dateInput].forEach(input => {
        input.removeAttribute('readonly');
        input.classList.remove('bg-gray-100', 'cursor-not-allowed');
        input.classList.add('bg-white');
    });

    document.getElementById('btnEditData').classList.add('hidden');
    document.getElementById('btnAddEvent').classList.add('hidden');
    document.getElementById('btnGoBack').classList.add('hidden');

    document.getElementById('btnDeleteSow').classList.remove('hidden');
    document.getElementById('btnCancelEdit').classList.remove('hidden');
    document.getElementById('btnSaveEdit').classList.remove('hidden');

    document.querySelectorAll('.action-col').forEach(col => {
        col.classList.remove('hidden');
    });
}

function cancelEditMode() {
    document.getElementById('sowForm').reset();

    const earInput = document.getElementById('ear_tag_input');
    const dateInput = document.getElementById('entry_date_input');

    [earInput, dateInput].forEach(input => {
        input.setAttribute('readonly', 'true');
        input.classList.add('bg-gray-100', 'cursor-not-allowed');
        input.classList.remove('bg-white');
    });

    document.getElementById('btnEditData').classList.remove('hidden');
    document.getElementById('btnAddEvent').classList.remove('hidden');
    document.getElementById('btnGoBack').classList.remove('hidden');
    document.getElementById('btnDeleteSow').classList.add('hidden');
    document.getElementById('btnCancelEdit').classList.add('hidden');
    document.getElementById('btnSaveEdit').classList.add('hidden');

    document.querySelectorAll('.action-col').forEach(col => {
        col.classList.add('hidden');
    });
}

function openDeleteModal() {
    document.getElementById('deleteModal').classList.remove('hidden');
    document.getElementById('confirmEarTag').focus();
}

var controlEarTagValue = '';

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
    document.getElementById('confirmEarTag').value = '';
    checkDeleteConfirmation(controlEarTagValue);
}

function checkDeleteConfirmation(expectedValue) {
    const input = document.getElementById('confirmEarTag').value;
    const btn = document.getElementById('deleteBtn');

    if (input === expectedValue) {
        btn.disabled = false;
        btn.classList.remove('bg-gray-400', 'cursor-not-allowed');
        btn.classList.add('bg-red-600', 'hover:bg-red-700');
    } else {
        btn.disabled = true;
        btn.classList.add('bg-gray-400', 'cursor-not-allowed');
        btn.classList.remove('bg-red-600', 'hover:bg-red-700');
    }
}

// Ustaw globalną wartość po załadowaniu strony
document.addEventListener('DOMContentLoaded', () => {
    const earTagInput = document.getElementById('confirmEarTag');
    if (earTagInput) {
        controlEarTagValue = earTagInput.placeholder;
    }
});
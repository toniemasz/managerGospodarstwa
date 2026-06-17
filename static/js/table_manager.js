class PaginationTable {
    constructor(config = {}) {
        this.config = config;

        this.table = this.resolveTable(config);
        if (this.table && this.table.paginationTableInstance) {
            return this.table.paginationTableInstance;
        }

        this.rows = this.resolveRows(config);
        if (!this.table && this.rows.length) {
            this.table = this.rows[0].closest('table');
        }
        this.scope = this.resolveScope(config);

        if (this.table) {
            this.table.dataset.paginationInitialized = 'true';
            this.table.paginationTableInstance = this;
        }

        this.searchInput = this.resolveElement(config.searchInputId, [
            'input[type="search"]',
            'input[data-table-search]',
            '.table-search',
            '.table-footer-controls input[type="text"]',
            '.filter-bar input[type="text"]'
        ]);

        this.filterSelect = this.resolveElement(config.filterSelectId, [
            'select[data-table-filter]',
            '.table-filter',
            '.table-footer-controls select[data-filter]',
            '.table-footer-controls select[id*="status" i]',
            '.table-footer-controls select[id*="filter" i]',
            '.filter-bar select[id*="status" i]',
            '.filter-bar select[id*="filter" i]'
        ]);

        this.limitSelect = this.resolveElement(config.limitSelectId, [
            'select[data-table-limit]',
            '.table-limit',
            '.table-footer-controls select[id*="limit" i]',
            '.table-footer-controls select[id*="per-page" i]',
            '.table-footer-controls select[id*="page" i]'
        ]);

        this.paginationContainer = this.resolvePaginationContainer(config.paginationContainerId);

        this.currentPage = 1;
        this.limit = this.getInitialLimit();
        this.filteredRows = [...this.rows];

        this.prepareControlsLayout();

        if (!this.rows.length) {
            return;
        }

        this.prepareRows();
        this.initEvents();
        this.filterData();
    }

    resolveTable(config) {
        if (config.tableId) {
            const table = document.getElementById(config.tableId);
            if (table) return table;
        }

        if (config.tableSelector) {
            const table = document.querySelector(config.tableSelector);
            if (table) return table;
        }

        if (config.rowSelector) {
            const row = document.querySelector(config.rowSelector);
            if (row) return row.closest('table');
        }

        return null;
    }

    filterDataRows(rows) {
        return rows.filter((row) => {
            if (row.dataset.paginationEmpty === 'true') return false;
            if (row.querySelector('.empty-table')) return false;
            return row.querySelectorAll('td').length > 0;
        });
    }

    resolveRows(config) {
        if (config.rowSelector) {
            const rows = this.filterDataRows(Array.from(document.querySelectorAll(config.rowSelector)));
            if (rows.length) return rows;
        }

        const table = this.table || (config.tableId ? document.getElementById(config.tableId) : null);
        if (table) {
            return this.filterDataRows(Array.from(table.querySelectorAll('tbody tr')));
        }

        return [];
    }

    resolveScope(config) {
        if (config.scopeSelector) {
            const scope = document.querySelector(config.scopeSelector);
            if (scope) return scope;
        }

        if (this.table) {
            return (
                this.table.closest('.panel') ||
                this.table.closest('.table-panel') ||
                this.table.parentElement ||
                document
            );
        }

        return document;
    }

    resolveElement(id, fallbackSelectors = []) {
        if (id) {
            const element = document.getElementById(id);
            if (element) return element;
        }

        for (const selector of fallbackSelectors) {
            const element = this.scope.querySelector(selector);
            if (element) return element;
        }

        return null;
    }

    resolvePaginationContainer(id) {
        if (id) {
            const element = document.getElementById(id);
            if (element) return element;
        }

        let element = this.scope.querySelector(
            '[data-table-pagination], .pagination-controls, .pagination-container'
        );

        if (element) return element;

        if (this.table) {
            element = document.createElement('div');
            element.className = 'pagination-controls';
            const tableWrapper = this.table.closest('.table-scroll, .overflow-x-auto') || this.table;
            tableWrapper.insertAdjacentElement('afterend', element);
            return element;
        }

        return null;
    }

    getInitialLimit() {
        if (!this.limitSelect) return 10;

        const value = parseInt(this.limitSelect.value, 10);
        return Number.isNaN(value) || value <= 0 ? 10 : value;
    }

    prepareControlsLayout() {
        const controls = this.scope.querySelector('.table-footer-controls');
        const tableWrapper = this.table
            ? this.table.closest('.table-scroll, .overflow-x-auto')
            : null;

        if (controls && tableWrapper) {
            const heading = this.scope.querySelector('.section-heading');

            if (heading && controls.previousElementSibling !== heading) {
                heading.insertAdjacentElement('afterend', controls);
            } else if (!heading && controls.compareDocumentPosition(tableWrapper) & Node.DOCUMENT_POSITION_PRECEDING) {
                tableWrapper.parentNode.insertBefore(controls, tableWrapper);
            }
        }

        if (this.searchInput && !this.searchInput.placeholder) {
            this.searchInput.placeholder = 'Wpisz szukaną frazę...';
        }

        if (this.searchInput) {
            this.searchInput.setAttribute('autocomplete', 'off');
        }
    }

    prepareRows() {
        this.rows.forEach((row) => {
            if (!row.dataset.originalDisplay) {
                row.dataset.originalDisplay = row.style.display || '';
            }

            if (!row.dataset.search) {
                row.dataset.search = row.textContent.trim();
            }

            if (!row.dataset.filter) {
                row.dataset.filter =
                    row.dataset.status ||
                    row.dataset.type ||
                    row.dataset.category ||
                    'ALL';
            }
        });
    }

    initEvents() {
        if (this.searchInput && this.searchInput.dataset.tableManagerSearchBound !== 'true') {
            this.searchInput.dataset.tableManagerSearchBound = 'true';
            this.searchInput.addEventListener('input', () => this.filterData());
        }

        if (this.filterSelect && this.filterSelect.dataset.tableManagerFilterBound !== 'true') {
            this.filterSelect.dataset.tableManagerFilterBound = 'true';
            this.filterSelect.addEventListener('change', () => this.filterData());
        }

        if (this.limitSelect && this.limitSelect.dataset.tableManagerLimitBound !== 'true') {
            this.limitSelect.dataset.tableManagerLimitBound = 'true';
            this.limitSelect.addEventListener('change', (event) => {
                const value = parseInt(event.target.value, 10);
                this.limit = Number.isNaN(value) || value <= 0 ? 10 : value;
                this.currentPage = 1;
                this.filterData();
            });
        }
    }

    normalize(value) {
        return String(value || '')
            .toLowerCase()
            .trim()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    getRowSearchText(row) {
        return this.normalize(
            row.dataset.search ||
            row.getAttribute('data-search') ||
            row.textContent ||
            ''
        );
    }

    getRowFilterValue(row) {
        return String(
            row.dataset.filter ||
            row.dataset.status ||
            row.dataset.type ||
            row.dataset.category ||
            'ALL'
        );
    }

    filterData() {
        const query = this.normalize(this.searchInput ? this.searchInput.value : '');
        const filterValue = this.filterSelect ? String(this.filterSelect.value || 'ALL') : 'ALL';

        this.filteredRows = this.rows.filter((row) => {
            const searchData = this.getRowSearchText(row);
            const rowFilterValue = this.getRowFilterValue(row);

            const matchesSearch = !query || searchData.includes(query);
            const matchesFilter =
                filterValue === 'ALL' ||
                filterValue === '' ||
                rowFilterValue === filterValue;

            return matchesSearch && matchesFilter;
        });

        this.currentPage = 1;
        this.updateTable();
    }

    hideRow(row) {
        row.hidden = true;
        row.style.display = 'none';
        row.classList.add('is-hidden-by-table-manager');
    }

    showRow(row) {
        row.hidden = false;
        row.style.display = row.dataset.originalDisplay || '';
        row.classList.remove('is-hidden-by-table-manager');
    }

    updateTable() {
        this.rows.forEach((row) => this.hideRow(row));

        const totalPages = Math.max(1, Math.ceil(this.filteredRows.length / this.limit));

        if (this.currentPage > totalPages) {
            this.currentPage = totalPages;
        }

        const start = (this.currentPage - 1) * this.limit;
        const end = start + this.limit;
        const rowsToShow = this.filteredRows.slice(start, end);

        rowsToShow.forEach((row) => this.showRow(row));

        this.renderEmptyState(rowsToShow.length === 0);
        this.renderPagination();
    }

    renderEmptyState(shouldShow) {
        if (!this.table) return;

        let emptyRow = this.table.querySelector('tr[data-pagination-empty="true"]');
        const columnCount = Math.max(
            1,
            this.table.querySelectorAll('thead th').length ||
            this.table.querySelectorAll('tbody tr:first-child td').length
        );

        if (!emptyRow) {
            emptyRow = document.createElement('tr');
            emptyRow.dataset.paginationEmpty = 'true';
            emptyRow.innerHTML = `<td colspan="${columnCount}" class="empty-table">Brak wyników dla wybranych filtrów.</td>`;
            const tbody = this.table.querySelector('tbody');
            if (tbody) tbody.appendChild(emptyRow);
        }

        emptyRow.hidden = !shouldShow;
        emptyRow.style.display = shouldShow ? '' : 'none';
    }

    renderPagination() {
        if (!this.paginationContainer) return;

        this.paginationContainer.innerHTML = '';
        this.paginationContainer.className = 'pagination-controls';

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
        buttons.className = 'pagination-buttons';

        buttons.appendChild(this.createButton('‹', this.currentPage === 1, () => {
            this.currentPage -= 1;
            this.updateTable();
        }));

        const pages = this.getVisiblePages(totalPages);

        pages.forEach((page) => {
            if (page === '...') {
                const ellipsis = document.createElement('span');
                ellipsis.className = 'pagination-ellipsis';
                ellipsis.innerText = '…';
                buttons.appendChild(ellipsis);
                return;
            }

            buttons.appendChild(this.createButton(String(page), false, () => {
                this.currentPage = page;
                this.updateTable();
            }, page === this.currentPage));
        });

        buttons.appendChild(this.createButton('›', this.currentPage === totalPages, () => {
            this.currentPage += 1;
            this.updateTable();
        }));

        this.paginationContainer.appendChild(buttons);
    }

    getVisiblePages(totalPages) {
        if (totalPages <= 7) {
            return Array.from({ length: totalPages }, (_, index) => index + 1);
        }

        const pages = [1];
        const start = Math.max(2, this.currentPage - 1);
        const end = Math.min(totalPages - 1, this.currentPage + 1);

        if (start > 2) pages.push('...');

        for (let page = start; page <= end; page += 1) {
            pages.push(page);
        }

        if (end < totalPages - 1) pages.push('...');

        pages.push(totalPages);
        return pages;
    }

    createButton(label, disabled, onClick, isActive = false) {
        const button = document.createElement('button');
        button.type = 'button';
        button.innerText = label;
        button.disabled = disabled;
        button.setAttribute('aria-label', this.getButtonLabel(label, isActive));
        if (isActive) {
            button.setAttribute('aria-current', 'page');
        }
        button.className = [
            'pagination-button',
            isActive ? 'is-active' : '',
            disabled ? 'is-disabled' : ''
        ].filter(Boolean).join(' ');

        if (!disabled) {
            button.addEventListener('click', onClick);
        }

        return button;
    }

    getButtonLabel(label, isActive) {
        if (label === '‹') return 'Poprzednia strona';
        if (label === '›') return 'Następna strona';
        return isActive ? `Strona ${label}, aktualna` : `Przejdź do strony ${label}`;
    }
}

function enhanceDataTable(table) {
    if (!table || table.dataset.enhanced === 'true') {
        return;
    }

    table.dataset.enhanced = 'true';
    table.classList.add('data-table');

    const parent = table.parentElement;
    const alreadyWrapped = parent && (
        parent.classList.contains('table-scroll') ||
        parent.classList.contains('data-table-scroll') ||
        parent.classList.contains('overflow-x-auto')
    );

    if (!alreadyWrapped && table.parentNode) {
        const wrapper = document.createElement('div');
        wrapper.className = 'table-scroll';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
    }

    const shell = table.closest('.panel, .table-card');
    if (shell) {
        shell.classList.add('table-card');
    }

    const headers = Array.from(table.querySelectorAll('thead th')).map((header) =>
        header.textContent.trim()
    );

    const isEditable = hasEditableTableFields(table);
    const wantsMobileCards = table.dataset.mobileCards === 'true';
    const blocksMobileCards = table.dataset.mobileCards === 'false';

    if (isEditable || table.classList.contains('settlement-table') || table.classList.contains('bulk-event-table')) {
        table.classList.add('wide-table');
    } else if (!blocksMobileCards && (wantsMobileCards || headers.length <= 6)) {
        table.classList.add('mobile-card-table');
    }

    table.querySelectorAll('tbody tr').forEach((row) => {
        if (row.dataset.paginationEmpty === 'true') return;

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

function hasEditableTableFields(table) {
    return Boolean(table.querySelector(
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea'
    ));
}

function autoInitPaginationTables() {
    document.querySelectorAll('table').forEach((table, index) => {
        if (table.dataset.paginationInitialized === 'true') return;
        if (table.closest('[data-no-pagination="true"]')) return;
        if (table.dataset.noPagination === 'true') return;
        if (table.dataset.tablePagination === 'false') return;
        if (hasEditableTableFields(table)) return;

        const tbody = table.querySelector('tbody');
        if (!tbody) return;

        const tbodyRows = Array.from(
            tbody.querySelectorAll('tr:not([data-pagination-empty="true"])')
        ).filter((row) => row.querySelectorAll('td').length > 0 && !row.querySelector('.empty-table'));

        if (!tbodyRows.length) return;

        if (!table.id) {
            table.id = `auto-table-${index + 1}`;
        }

        const rowClass = `${table.id}-row`;

        tbodyRows.forEach((row) => {
            row.classList.add(rowClass);

            if (!row.dataset.search) {
                row.dataset.search = row.textContent.trim();
            }

            if (!row.dataset.filter) {
                row.dataset.filter =
                    row.dataset.status ||
                    row.dataset.type ||
                    row.dataset.category ||
                    'ALL';
            }
        });

        ensureTableControls(table);

        new PaginationTable({
            rowSelector: `#${table.id} tbody tr.${rowClass}:not([data-pagination-empty="true"])`,
            tableId: table.id,
            searchInputId: table.dataset.searchInput || null,
            filterSelectId: table.dataset.filterSelect || null,
            limitSelectId: table.dataset.limitSelect || null,
            paginationContainerId: table.dataset.paginationTarget || null
        });
    });
}

function ensureTableControls(table) {
    const panel =
        table.closest('.panel') ||
        table.closest('.table-card') ||
        table.closest('section') ||
        table.parentElement;

    if (!panel) return;

    let controls = panel.querySelector('.table-footer-controls');
    const tableWrapper = table.closest('.table-scroll, .overflow-x-auto') || table.parentElement;

    if (!controls) {
        controls = document.createElement('div');
        controls.className = 'table-footer-controls';
        controls.dataset.autoCreated = 'true';

        const searchLabel = table.dataset.searchLabel || 'Szukaj';
        const searchPlaceholder = table.dataset.searchPlaceholder || 'Wpisz szukaną frazę...';
        const limitLabel = table.dataset.limitLabel || 'Na stronę';

        controls.innerHTML = `
            <div class="table-control">
                <label for="${table.id}-search">${searchLabel}</label>
                <input type="search" id="${table.id}-search" class="table-search" placeholder="${searchPlaceholder}" data-table-search>
            </div>
            <div class="table-control">
                <label for="${table.id}-limit">${limitLabel}</label>
                <select id="${table.id}-limit" class="table-limit" data-table-limit>
                    <option value="10">10</option>
                    <option value="25">25</option>
                    <option value="50">50</option>
                    <option value="100">100</option>
                </select>
            </div>
        `;
    }

    const heading = panel.querySelector('.section-heading');

    if (heading && controls.previousElementSibling !== heading) {
        heading.insertAdjacentElement('afterend', controls);
    } else if (tableWrapper && controls.compareDocumentPosition(tableWrapper) & Node.DOCUMENT_POSITION_PRECEDING) {
        tableWrapper.parentNode.insertBefore(controls, tableWrapper);
    } else if (tableWrapper && !panel.contains(controls)) {
        tableWrapper.parentNode.insertBefore(controls, tableWrapper);
    }
}

function getResizeText(field) {
    if (field.tagName === 'SELECT') {
        const option = field.options[field.selectedIndex];
        return option ? option.text : '';
    }

    return field.value || field.placeholder || field.getAttribute('aria-label') || '';
}

function resizeAutoField(field) {
    if (!field || field.type === 'checkbox' || field.type === 'radio' || field.type === 'hidden') {
        return;
    }

    const isTableField = Boolean(field.closest('table'));
    const text = getResizeText(field);
    const min = parseInt(field.dataset.autoResizeMin || '', 10) || (field.tagName === 'SELECT' ? 10 : 6);
    const max = parseInt(field.dataset.autoResizeMax || '', 10) || (isTableField ? 44 : 72);
    const width = Math.min(max, Math.max(min, text.length + 2));

    field.style.width = `${width}ch`;
    field.style.maxWidth = '100%';

    if (field.tagName === 'TEXTAREA') {
        field.style.height = 'auto';
        field.style.height = `${Math.max(field.scrollHeight, 44)}px`;
    }
}

function bindAutoResizeField(field) {
    if (!field || field.dataset.autoResizeBound === 'true') return;

    field.dataset.autoResizeBound = 'true';
    field.classList.add('auto-resize-field');
    resizeAutoField(field);

    field.addEventListener('input', () => resizeAutoField(field));
    field.addEventListener('change', () => resizeAutoField(field));
}

function enhanceAutoResizeFields(root = document) {
    const selector = [
        'table input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"])',
        'table select',
        'table textarea',
        '.bulk-event-input',
        '.settlement-input',
        '.form-field input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"])',
        '.form-field select',
        '.form-field textarea'
    ].join(', ');

    root.querySelectorAll(selector).forEach(bindAutoResizeField);
}


document.addEventListener('DOMContentLoaded', () => {
    enhanceDataTables();
    autoInitPaginationTables();
    enhanceAutoResizeFields();
});

window.PaginationTable = PaginationTable;
window.enhanceDataTables = enhanceDataTables;
window.enhanceAutoResizeFields = enhanceAutoResizeFields;

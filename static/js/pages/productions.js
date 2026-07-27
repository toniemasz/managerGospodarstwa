document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('[data-bulk-production-form]');
    if (!form) return;

    const selectAll = form.querySelector('[data-select-all-productions]');
    const checkboxes = Array.from(form.querySelectorAll('[data-production-checkbox]'));
    const counter = form.querySelector('[data-selected-production-count]');
    const submitButton = form.querySelector('[data-bulk-complete-button]');
    const dialog = form.querySelector('[data-bulk-production-dialog]');
    if (!selectAll || !counter || !submitButton) return;

    const selectedCheckboxes = () => checkboxes.filter((checkbox) => checkbox.checked);
    const updateState = () => {
        const selectedCount = selectedCheckboxes().length;
        counter.textContent = `Wybrano: ${selectedCount}`;
        submitButton.disabled = selectedCount === 0;
        selectAll.disabled = checkboxes.length === 0;
        selectAll.checked = checkboxes.length > 0 && selectedCount === checkboxes.length;
        selectAll.indeterminate = selectedCount > 0 && selectedCount < checkboxes.length;
    };

    selectAll.addEventListener('change', () => {
        checkboxes.forEach((checkbox) => { checkbox.checked = selectAll.checked; });
        updateState();
    });
    checkboxes.forEach((checkbox) => checkbox.addEventListener('change', updateState));
    submitButton.addEventListener('click', () => {
        const selected = selectedCheckboxes();
        if (!selected.length || !dialog) return;
        const statuses = selected.map((checkbox) => checkbox.closest('tr')?.dataset.productionStatus);
        dialog.querySelector('[data-ready-production-count]').textContent = statuses.filter((status) => status === 'STAGE_1_DONE').length;
        dialog.querySelector('[data-skipped-stage-count]').textContent = statuses.filter((status) => status === 'QUEUED').length;
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
    });
    dialog?.querySelectorAll('[data-bulk-dialog-close]').forEach((button) => {
        button.addEventListener('click', () => {
            if (typeof dialog.close === 'function') dialog.close();
            else dialog.removeAttribute('open');
        });
    });
    updateState();
});

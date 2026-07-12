document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('[data-bulk-production-form]');
    if (!form) return;

    const selectAll = form.querySelector('[data-select-all-productions]');
    const checkboxes = Array.from(form.querySelectorAll('[data-production-checkbox]'));
    const counter = form.querySelector('[data-selected-production-count]');
    const submitButton = form.querySelector('[data-bulk-complete-button]');
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
    form.addEventListener('submit', (event) => {
        const selectedCount = selectedCheckboxes().length;
        if (!selectedCount || !window.confirm(`Zakończyć zaznaczone śrutowania (${selectedCount})?`)) {
            event.preventDefault();
            updateState();
        }
    });
    updateState();
});

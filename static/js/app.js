document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.table-footer-controls input[type="text"]').forEach((input) => {
        if (!input.placeholder) input.placeholder = 'Wpisz szukaną frazę...';
    });
});

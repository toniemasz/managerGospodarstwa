(() => {
    const slider = document.querySelector('[data-font-scale-slider]');
    const numberInput = document.querySelector('[data-font-scale-number]');
    const output = document.querySelector('[data-font-scale-output]');
    if (!slider || !numberInput) return;

    const clamp = (value) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isNaN(parsed) ? 100 : Math.min(200, Math.max(20, parsed));
    };
    const render = (value) => {
        slider.value = value;
        numberInput.value = value;
        if (output) output.textContent = `${value}%`;
    };

    slider.addEventListener('input', () => render(clamp(slider.value)));
    numberInput.addEventListener('input', () => {
        if (numberInput.value === '') return;
        slider.value = clamp(numberInput.value);
        if (output) output.textContent = `${slider.value}%`;
    });
    numberInput.addEventListener('change', () => render(clamp(numberInput.value)));
    render(clamp(numberInput.value || slider.value));
})();

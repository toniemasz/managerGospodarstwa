(() => {
    const form = document.querySelector('[data-settings-form]');
    const slider = document.querySelector('[data-font-scale-slider]');
    const numberInput = document.querySelector('[data-font-scale-number]');
    const output = document.querySelector('[data-font-scale-output]');
    if (!slider || !numberInput) return;

    const clamp = (value) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isNaN(parsed) ? 100 : Math.min(150, Math.max(80, parsed));
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
    document.querySelectorAll('[data-font-scale-preset]').forEach((button) => {
        button.addEventListener('click', () => {
            render(clamp(button.dataset.fontScalePreset));
            numberInput.dispatchEvent(new Event('input', { bubbles: true }));
        });
    });
    render(clamp(numberInput.value || slider.value));

    if (!form) return;

    form.querySelectorAll('[data-module-setting]').forEach((moduleCard) => {
        const visible = moduleCard.querySelector('input[name^="show_"]');
        const pinned = moduleCard.querySelector('input[name^="nav_"]');
        const help = moduleCard.querySelector('[data-module-disabled-help]');
        if (!visible || !pinned) return;

        const syncModule = () => {
            pinned.disabled = !visible.checked;
            if (!visible.checked) pinned.checked = false;
            if (help) help.hidden = visible.checked;
        };
        visible.addEventListener('change', syncModule);
        syncModule();
    });

    const saveButtons = Array.from(document.querySelectorAll('[data-settings-save]'));
    const unsavedNotice = document.querySelector('[data-settings-unsaved]');
    const snapshot = () => JSON.stringify(
        Array.from(new FormData(form).entries())
            .filter(([name]) => name !== 'csrfmiddlewaretoken')
            .map(([name, value]) => [name, String(value)])
            .sort(([left], [right]) => left.localeCompare(right))
    );
    const initialSnapshot = snapshot();
    let isDirty = false;
    const syncDirtyState = () => {
        isDirty = snapshot() !== initialSnapshot;
        saveButtons.forEach((button) => {
            button.disabled = !isDirty;
        });
        if (unsavedNotice) unsavedNotice.hidden = !isDirty;
    };

    form.addEventListener('input', syncDirtyState);
    form.addEventListener('change', syncDirtyState);
    form.addEventListener('submit', () => {
        isDirty = false;
    });
    window.addEventListener('beforeunload', (event) => {
        if (!isDirty) return;
        event.preventDefault();
        event.returnValue = '';
    });
    syncDirtyState();
})();

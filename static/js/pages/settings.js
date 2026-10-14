(() => {
    const form = document.querySelector('[data-settings-form]');
    const slider = document.querySelector('[data-font-scale-slider]');
    const numberInput = document.querySelector('[data-font-scale-number]');
    const output = document.querySelector('[data-font-scale-output]');
    const customPanel = document.querySelector('[data-font-scale-custom]');
    const customToggle = document.querySelector('[data-font-scale-custom-toggle]');
    if (!slider || !numberInput) return;

    const clamp = (value) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isNaN(parsed) ? 100 : Math.min(150, Math.max(80, parsed));
    };
    const render = (value) => {
        slider.value = value;
        numberInput.value = value;
        if (output) output.textContent = `${value}%`;
        document.documentElement.style.setProperty('--user-font-scale', String(value / 100));
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
            if (customPanel) customPanel.hidden = true;
            customToggle?.setAttribute('aria-expanded', 'false');
            numberInput.dispatchEvent(new Event('input', { bubbles: true }));
        });
    });
    customToggle?.addEventListener('click', () => {
        const expanded = customToggle.getAttribute('aria-expanded') === 'true';
        customToggle.setAttribute('aria-expanded', String(!expanded));
        if (customPanel) customPanel.hidden = expanded;
        if (!expanded) slider.focus();
    });
    if (![90, 100, 120, 140].includes(clamp(numberInput.value))) {
        if (customPanel) customPanel.hidden = false;
        customToggle?.setAttribute('aria-expanded', 'true');
    }
    render(clamp(numberInput.value || slider.value));

    const tabs = Array.from(document.querySelectorAll('[data-settings-tab]'));
    const panels = Array.from(document.querySelectorAll('[data-settings-panel]'));
    const saveBar = document.querySelector('.settings-save-bar');
    const selectPanel = (name, updateHash = true) => {
        const safeName = panels.some((panel) => panel.dataset.settingsPanel === name) ? name : 'general';
        tabs.forEach((tab) => {
            const active = tab.dataset.settingsTab === safeName;
            tab.classList.toggle('is-active', active);
            tab.setAttribute('aria-selected', String(active));
            tab.tabIndex = active ? 0 : -1;
        });
        panels.forEach((panel) => {
            panel.hidden = panel.dataset.settingsPanel !== safeName;
        });
        if (saveBar) saveBar.hidden = safeName === 'data';
        if (updateHash) history.replaceState(null, '', `#settings-${safeName}`);
    };
    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectPanel(tab.dataset.settingsTab));
        tab.addEventListener('keydown', (event) => {
            let targetIndex = null;
            if (event.key === 'ArrowRight') targetIndex = (index + 1) % tabs.length;
            if (event.key === 'ArrowLeft') targetIndex = (index - 1 + tabs.length) % tabs.length;
            if (event.key === 'Home') targetIndex = 0;
            if (event.key === 'End') targetIndex = tabs.length - 1;
            if (targetIndex === null) return;
            event.preventDefault();
            tabs[targetIndex].focus();
            selectPanel(tabs[targetIndex].dataset.settingsTab);
        });
    });
    const errorPanel = panels.find((panel) => panel.querySelector('.errorlist'))?.dataset.settingsPanel;
    const hashPanel = window.location.hash.replace('#settings-', '');
    selectPanel(errorPanel || hashPanel || 'general', false);

    const previewChoice = (name, classPrefix, bodyPrefix = null) => {
        form?.querySelectorAll(`[name="${name}"]`).forEach((radio) => {
            radio.addEventListener('change', () => {
                document.documentElement.className = document.documentElement.className
                    .split(/\s+/)
                    .filter((className) => !className.startsWith(classPrefix))
                    .concat(`${classPrefix}${radio.value}`)
                    .join(' ');
                if (bodyPrefix) {
                    document.body.className = document.body.className
                        .split(/\s+/)
                        .filter((className) => !className.startsWith(bodyPrefix))
                        .concat(`${bodyPrefix}${radio.value}`)
                        .join(' ');
                }
            });
        });
    };
    previewChoice('theme', 'theme-');
    previewChoice('interface_scale', 'ui-density-', 'ui-scale-');

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

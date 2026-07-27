(function () {
    function parseJson(value, fallback) {
        if (!value) return fallback;
        try {
            return JSON.parse(value);
        } catch (error) {
            return fallback;
        }
    }

    function parseJsonScript(elementId, fallback) {
        if (!elementId) return fallback;
        const element = document.getElementById(elementId);
        return parseJson(element?.textContent, fallback);
    }

    function setFieldState(field, enabled, shouldClear) {
        if (!field) return;

        const container = field.closest('.form-field, td');
        field.disabled = !enabled;
        field.toggleAttribute('aria-disabled', !enabled);
        field.classList.toggle('cursor-not-allowed', !enabled);

        if (container) {
            container.classList.toggle('is-muted', !enabled);
            container.classList.toggle('disabled-cell', !enabled);
        }

        if (!enabled && shouldClear) {
            if (field.tagName === 'SELECT') {
                field.selectedIndex = 0;
            } else if (field.type === 'checkbox') {
                field.checked = false;
            } else {
                field.value = '';
            }
        }
    }

    function initDateRangeFilters(root = document) {
        root.querySelectorAll('select[name="period"], select#period').forEach((periodSelect) => {
            if (periodSelect.dataset.dateRangeBound === 'true') return;

            const form = periodSelect.closest('form') || root;
            const dateInputs = Array.from(form.querySelectorAll('input[name="date_from"], input[name="date_to"]'));
            if (!dateInputs.length) return;

            periodSelect.dataset.dateRangeBound = 'true';

            const syncDateInputs = () => {
                const isCustom = periodSelect.value === 'custom';
                dateInputs.forEach((input) => {
                    input.disabled = !isCustom;
                    input.closest('.table-control, .form-field')?.classList.toggle('is-muted', !isCustom);
                });
            };

            periodSelect.addEventListener('change', syncDateInputs);
            syncDateInputs();
        });
    }

    function initTrendCharts(root = document) {
        root.querySelectorAll('canvas[data-chart-type="line"]').forEach((canvas) => {
            if (canvas.dataset.chartInitialized === 'true') return;

            const labels = parseJsonScript(canvas.dataset.chartLabelsId, []);
            const values = parseJsonScript(canvas.dataset.chartValuesId, []);
            const configuredDatasets = parseJsonScript(canvas.dataset.chartDatasetsId, []);
            const label = canvas.dataset.chartLabel || 'Wynik';
            const message = canvas.parentElement?.querySelector('[data-chart-message]');

            const showMessage = (text) => {
                canvas.hidden = true;
                if (message) {
                    message.textContent = text;
                    message.hidden = false;
                }
            };

            if (!labels.length || (!values.length && !configuredDatasets.length)) {
                showMessage('Brak danych dla wybranej metryki i zakresu dat.');
                return;
            }

            if (!window.Chart) {
                showMessage('Nie udało się załadować wykresu. Odśwież stronę i spróbuj ponownie.');
                return;
            }

            canvas.dataset.chartInitialized = 'true';

            const datasets = configuredDatasets.length
                ? configuredDatasets.map((dataset) => ({
                    borderWidth: 3,
                    tension: 0.25,
                    fill: false,
                    pointRadius: 3,
                    ...dataset
                }))
                : [{
                    label,
                    data: values,
                    borderColor: '#2364aa',
                    backgroundColor: 'rgba(35, 100, 170, 0.12)',
                    borderWidth: 3,
                    tension: 0.25,
                    fill: true,
                    pointRadius: 4
                }];

            new window.Chart(canvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels,
                    datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });
        });
    }

    function initSingleSowEventForm(root = document) {
        const typeSelect = root.getElementById?.('id_event_type') || document.getElementById('id_event_type');
        if (!typeSelect || typeSelect.dataset.dynamicFieldsBound === 'true') return;

        const sections = {
            INSEMINATION: document.getElementById('sec_insemination'),
            PREGNANCY_CHECK: document.getElementById('sec_pregnancy_check'),
            FARROWING: document.getElementById('sec_farrowing'),
            WEANING: document.getElementById('sec_weaning'),
            MISCARRIAGE: document.getElementById('sec_miscarriage'),
            VACCINATION: document.getElementById('sec_vaccination')
        };

        const fieldsByType = {
            INSEMINATION: ['id_technician'],
            PREGNANCY_CHECK: ['id_pregnancy_result'],
            FARROWING: ['id_born_alive', 'id_born_dead'],
            WEANING: ['id_count'],
            MISCARRIAGE: [],
            VACCINATION: ['id_vaccine_name']
        };

        const allDynamicFieldIds = [
            'id_technician',
            'id_pregnancy_result',
            'id_born_alive',
            'id_born_dead',
            'id_count',
            'id_vaccine_name'
        ];

        const toggleFields = (shouldClear = false) => {
            const eventType = typeSelect.value;
            const activeFieldIds = fieldsByType[eventType] || [];

            Object.entries(sections).forEach(([type, section]) => {
                if (!section) return;
                const isActive = type === eventType;
                section.classList.toggle('hidden', !isActive);
                section.classList.toggle('is-muted', !isActive);
            });

            allDynamicFieldIds.forEach((fieldId) => {
                const field = document.getElementById(fieldId);
                setFieldState(field, activeFieldIds.includes(fieldId), shouldClear);
            });
        };

        typeSelect.dataset.dynamicFieldsBound = 'true';
        typeSelect.addEventListener('change', () => toggleFields(true));
        toggleFields(false);
    }

    function initBulkEventForm(root = document) {
        const rows = root.getElementById?.('bulk-event-rows') || document.getElementById('bulk-event-rows');
        if (!rows || rows.dataset.bulkEventsBound === 'true') return;

        const totalForms = document.getElementById('id_events-TOTAL_FORMS');
        const template = document.getElementById('bulk-event-row-template');
        const addButton = document.getElementById('add-bulk-event-row');

        const detailFieldRules = {
            INSEMINATION: ['technician'],
            PREGNANCY_CHECK: ['pregnancy_result'],
            FARROWING: ['born_alive', 'born_dead'],
            WEANING: ['count'],
            MISCARRIAGE: [],
            VACCINATION: ['vaccine_name']
        };

        const allDetailFields = [
            'technician',
            'pregnancy_result',
            'born_alive',
            'born_dead',
            'count',
            'vaccine_name'
        ];

        const getField = (row, fieldName) => row.querySelector(`[name$="-${fieldName}"]`);

        const updateRowFields = (row, shouldClear = false) => {
            const eventTypeField = getField(row, 'event_type');
            const eventType = eventTypeField ? eventTypeField.value : '';
            const enabledFields = detailFieldRules[eventType] || [];

            allDetailFields.forEach((fieldName) => {
                const field = getField(row, fieldName);
                const isEnabled = enabledFields.includes(fieldName);
                setFieldState(field, isEnabled, shouldClear);
                const container = field?.closest('td, .form-field');
                if (container) container.hidden = !isEnabled;
            });
        };

        const prepareRow = (row) => {
            const sowInput = getField(row, 'sow_ear_tag');
            const eventTypeField = getField(row, 'event_type');

            if (sowInput) {
                sowInput.setAttribute('list', 'sow-ear-tags');
                sowInput.setAttribute('placeholder', 'Nr kolczyka');
            }

            row.querySelectorAll('.copy-sow').forEach((button) => {
                button.setAttribute('aria-label', 'Skopiuj maciorę z poprzedniego wiersza');
            });

            if (eventTypeField && eventTypeField.dataset.dynamicFieldsBound !== 'true') {
                eventTypeField.dataset.dynamicFieldsBound = 'true';
                eventTypeField.addEventListener('change', () => updateRowFields(row, true));
            }

            updateRowFields(row, false);
        };

        const copyPreviousSow = (button) => {
            const row = button.closest('tr');
            const previous = row?.previousElementSibling;
            if (!previous) return;

            const source = getField(previous, 'sow_ear_tag');
            const target = getField(row, 'sow_ear_tag');
            if (source && target) target.value = source.value;
        };

        rows.dataset.bulkEventsBound = 'true';
        rows.querySelectorAll('.bulk-event-row').forEach(prepareRow);

        rows.addEventListener('click', (event) => {
            const button = event.target.closest('.copy-sow');
            if (button) copyPreviousSow(button);
            const removeButton = event.target.closest('.remove-bulk-event-row');
            if (removeButton) {
                const row = removeButton.closest('.bulk-event-row');
                const checkbox = getField(row, 'DELETE');
                if (checkbox) checkbox.checked = true;
                if (row) row.hidden = true;
            }
        });

        if (addButton && template && totalForms && addButton.dataset.bulkEventAddBound !== 'true') {
            addButton.dataset.bulkEventAddBound = 'true';
            addButton.addEventListener('click', () => {
                const index = parseInt(totalForms.value, 10);
                const html = template.innerHTML.replaceAll('__prefix__', index);

                rows.insertAdjacentHTML('beforeend', html);
                totalForms.value = index + 1;

                prepareRow(rows.lastElementChild);
                window.enhanceAutoResizeFields?.(rows.lastElementChild);
            });
        }

        const form = rows.closest('form');
        if (form && form.dataset.bulkEventsSubmitBound !== 'true') {
            form.dataset.bulkEventsSubmitBound = 'true';
            form.addEventListener('submit', () => {
                form.querySelectorAll(':disabled').forEach((field) => {
                    field.disabled = false;
                });
            });
        }
    }

    function initMortalityForm(root = document) {
        const form = root.getElementById?.('mortality-form') || document.getElementById('mortality-form');
        if (!form || form.dataset.mortalityBound === 'true') return;

        const typeSelect = form.querySelector('#id_mortality_type');
        const sowSection = document.getElementById('sec_mortality_sow');
        const sowField = form.querySelector('#id_sow');
        if (!typeSelect) return;

        const syncMortalityFields = (shouldClear = false) => {
            const isSow = typeSelect.value === 'MACIORA';
            const requiresSow = isSow;

            sowSection?.classList.toggle('hidden', !requiresSow);
            setFieldState(sowField, requiresSow, shouldClear);
        };

        form.dataset.mortalityBound = 'true';
        typeSelect.addEventListener('change', () => syncMortalityFields(true));
        syncMortalityFields(false);
    }


        function initVaccinationPlanForm(root = document) {
        const form = (
            root.getElementById?.('vaccination-plan-form')
            || document.getElementById('vaccination-plan-form')
        );

        if (!form || form.dataset.vaccinationPlanBound === 'true') return;

        const triggerType = form.querySelector('#id_trigger_type');
        const scope = form.querySelector('#id_scope');

        if (!triggerType || !scope) return;

        const triggerSections = {
            BEFORE_FARROWING: document.getElementById(
                'vaccination-before-farrowing-section'
            ),
            AFTER_EVENT: document.getElementById(
                'vaccination-after-event-section'
            ),
            INTERVAL: document.getElementById(
                'vaccination-interval-section'
            ),
        };

        const selectedSowsSection = document.getElementById(
            'vaccination-selected-sows-section'
        );
        const intervalValue = form.querySelector('#id_interval_value');
        const intervalUnit = form.querySelector('#id_interval_unit');
        const firstDueDate = form.querySelector('#id_first_due_date');
        const reminderDays = form.querySelector('#id_reminder_days_ahead');
        const scheduleMode = form.querySelector('#id_schedule_mode');
        const schedulePreview = form.querySelector('[data-vaccination-schedule-preview]');

        const setSectionState = (section, enabled, shouldClear = false) => {
            if (!section) return;

            section.hidden = !enabled;
            section.setAttribute('aria-hidden', String(!enabled));

            section.querySelectorAll('input, select, textarea').forEach((field) => {
                setFieldState(field, enabled, shouldClear);
            });
        };

        const syncTriggerSections = (shouldClear = false) => {
            const selectedType = triggerType.value;

            Object.entries(triggerSections).forEach(([type, section]) => {
                setSectionState(
                    section,
                    type === selectedType,
                    shouldClear,
                );
            });
        };

        const syncScopeSection = (shouldClear = false) => {
            setSectionState(
                selectedSowsSection,
                scope.value === 'SELECTED',
                shouldClear,
            );
        };

        const parseDate = (value) => {
            const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
            if (!match) return null;
            return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
        };
        const addInterval = (date, value, unit) => {
            const result = new Date(date.getTime());
            if (unit === 'DAYS' || unit === 'WEEKS') {
                result.setUTCDate(result.getUTCDate() + value * (unit === 'WEEKS' ? 7 : 1));
                return result;
            }
            const months = unit === 'YEARS' ? value * 12 : value;
            const targetMonth = result.getUTCMonth() + months;
            const targetYear = result.getUTCFullYear() + Math.floor(targetMonth / 12);
            const normalizedMonth = ((targetMonth % 12) + 12) % 12;
            const lastDay = new Date(Date.UTC(targetYear, normalizedMonth + 1, 0)).getUTCDate();
            result.setUTCFullYear(targetYear, normalizedMonth, Math.min(result.getUTCDate(), lastDay));
            return result;
        };
        const formatDate = (date) => new Intl.DateTimeFormat('pl-PL', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            timeZone: 'UTC'
        }).format(date);
        const updateSchedulePreview = () => {
            if (!schedulePreview) return;
            const first = parseDate(firstDueDate?.value);
            const value = Number.parseInt(intervalValue?.value || '', 10);
            const unit = intervalUnit?.value;
            const modeLabel = scheduleMode?.selectedOptions?.[0]?.textContent?.trim() || '—';
            const reminder = Number.parseInt(reminderDays?.value || '', 10);
            const firstOutput = schedulePreview.querySelector('[data-schedule-first]');
            const nextOutput = schedulePreview.querySelector('[data-schedule-next]');

            schedulePreview.querySelector('[data-schedule-mode]').textContent = `Tryb harmonogramu: ${modeLabel}`;
            schedulePreview.querySelector('[data-schedule-reminder]').textContent = Number.isFinite(reminder)
                ? `Przypomnienie: ${reminder} dni wcześniej`
                : 'Przypomnienie: —';
            if (!first || !Number.isFinite(value) || value < 1 || !unit) {
                firstOutput.textContent = 'Pierwszy termin: —';
                nextOutput.textContent = 'Kolejne terminy: —';
                return;
            }

            const dates = [first];
            for (let index = 0; index < 3; index += 1) {
                dates.push(addInterval(dates.at(-1), value, unit));
            }
            firstOutput.textContent = `Pierwszy termin: ${formatDate(dates[0])}`;
            nextOutput.textContent = `Kolejne terminy: ${dates.slice(1).map(formatDate).join(', ')}`;
        };

        const selectionOptions = Array.from(form.querySelectorAll('[data-sow-option]'));
        const selectionCheckboxes = selectionOptions
            .map((option) => option.querySelector('input[type="checkbox"]'))
            .filter(Boolean);
        const searchInput = form.querySelector('[data-sow-search]');
        const statusFilter = form.querySelector('[data-sow-status-filter]');
        const selectedCount = form.querySelector('[data-selected-count]');
        const updateSelection = () => {
            const search = (searchInput?.value || '').trim().toLocaleLowerCase('pl-PL');
            const status = (statusFilter?.value || '').toLocaleLowerCase('pl-PL');
            selectionOptions.forEach((option) => {
                const haystack = (option.dataset.search || option.textContent).toLocaleLowerCase('pl-PL');
                option.hidden = !haystack.includes(search) || !haystack.includes(status);
            });
            if (selectedCount) {
                selectedCount.textContent = `Wybrano: ${selectionCheckboxes.filter((checkbox) => checkbox.checked).length}`;
            }
        };

        form.dataset.vaccinationPlanBound = 'true';

        triggerType.addEventListener('change', () => {
            syncTriggerSections(true);
        });

        scope.addEventListener('change', () => {
            syncScopeSection(true);
        });
        [intervalValue, intervalUnit, firstDueDate, reminderDays, scheduleMode].forEach((field) => {
            field?.addEventListener('input', updateSchedulePreview);
            field?.addEventListener('change', updateSchedulePreview);
        });
        searchInput?.addEventListener('input', updateSelection);
        statusFilter?.addEventListener('change', updateSelection);
        selectionCheckboxes.forEach((checkbox) => checkbox.addEventListener('change', updateSelection));
        form.querySelector('[data-select-visible]')?.addEventListener('click', () => {
            selectionOptions.filter((option) => !option.hidden).forEach((option) => {
                option.querySelector('input[type="checkbox"]').checked = true;
            });
            updateSelection();
        });
        form.querySelector('[data-clear-selection]')?.addEventListener('click', () => {
            selectionCheckboxes.forEach((checkbox) => {
                checkbox.checked = false;
            });
            updateSelection();
        });

        syncTriggerSections(false);
        syncScopeSection(false);
        updateSchedulePreview();
        updateSelection();
    }


    function initTodayTaskForms(root = document) {
        root.querySelectorAll('.today-task-form').forEach((form) => {
            if (form.dataset.todayTasksBound === 'true') return;

            const submitButton = form.querySelector('.today-task-submit-button');
            const checkboxes = Array.from(form.querySelectorAll('.today-task-checkbox'));
            if (!checkboxes.length) return;

            const syncTaskRows = () => {
                const hasSelection = checkboxes.some((checkbox) => checkbox.checked);
                if (submitButton) submitButton.disabled = !hasSelection;

                checkboxes.forEach((checkbox) => {
                    const row = checkbox.closest('.today-task-row') || checkbox.closest('.today-task-dialog-item');
                    const resultSelect = row?.querySelector('.today-task-result');
                    row?.classList.toggle('is-selected', checkbox.checked);
                    if (resultSelect) {
                        resultSelect.disabled = !checkbox.checked;
                        resultSelect.required = checkbox.checked;
                    }
                });
            };

            form.dataset.todayTasksBound = 'true';
            checkboxes.forEach((checkbox) => {
                checkbox.addEventListener('change', syncTaskRows);
            });
            syncTaskRows();
        });
    }

    function initTodayTaskDialogs(root = document) {
        root.querySelectorAll('[data-dialog-open]').forEach((button) => {
            if (button.dataset.dialogOpenBound === 'true') return;

            button.dataset.dialogOpenBound = 'true';
            button.addEventListener('click', () => {
                const dialog = document.getElementById(button.dataset.dialogOpen);
                if (!dialog) return;

                if (typeof dialog.showModal === 'function') {
                    dialog.showModal();
                } else {
                    dialog.setAttribute('open', '');
                }
                dialog.querySelector('.today-task-checkbox')?.focus();
            });
        });

        root.querySelectorAll('.today-task-dialog').forEach((dialog) => {
            if (dialog.dataset.dialogCloseBound === 'true') return;

            const closeDialog = () => {
                if (typeof dialog.close === 'function') {
                    dialog.close();
                } else {
                    dialog.removeAttribute('open');
                }
            };

            dialog.dataset.dialogCloseBound = 'true';
            dialog.addEventListener('click', (event) => {
                if (event.target === dialog) closeDialog();
            });
            dialog.querySelectorAll('[data-dialog-close]').forEach((button) => {
                button.addEventListener('click', closeDialog);
            });
        });
    }

    function initSaleFormset(root = document) {
        const addButton = root.getElementById?.('add-settlement-row') || document.getElementById('add-settlement-row');
        const rows = document.getElementById('settlement-rows');
        const template = document.getElementById('settlement-row-template');
        const totalForms = document.getElementById('id_rows-TOTAL_FORMS');

        if (!addButton || !rows || !template || !totalForms || addButton.dataset.saleRowsBound === 'true') return;

        const emptyState = document.getElementById('settlement-rows-empty');
        const saleForm = document.getElementById('sale-form');
        const parseDecimal = (value) => {
            const parsed = Number.parseFloat(String(value || '').replace(/\s/g, '').replace(',', '.'));
            return Number.isFinite(parsed) ? parsed : null;
        };
        const setCalculatedValue = (input, value) => {
            if (!input || value === null || !Number.isFinite(value)) return;
            if (input.value.trim() && input.dataset.calculated !== 'true') return;
            input.value = value.toFixed(2).replace('.', ',');
            input.dataset.calculated = 'true';
        };
        const calculateRow = (row) => {
            if (!row || row.hidden) return;
            const quantity = parseDecimal(row.querySelector('input[name$="-quantity"]')?.value);
            const weight = parseDecimal(row.querySelector('input[name$="-weight"]')?.value);
            const price = parseDecimal(row.querySelector('input[name$="-price_per_kg"]')?.value);
            const vat = parseDecimal(row.querySelector('input[name$="-vat_value"]')?.value);
            const netInput = row.querySelector('input[name$="-net_value"]');
            const net = weight !== null && price !== null ? weight * price : parseDecimal(netInput?.value);

            if (quantity && weight !== null) {
                setCalculatedValue(row.querySelector('input[name$="-avg_weight"]'), weight / quantity);
            }
            if (weight !== null && price !== null) setCalculatedValue(netInput, net);
            if (net !== null && vat !== null) {
                setCalculatedValue(row.querySelector('input[name$="-gross_value"]'), net + vat);
            }
        };
        const updateEmptyState = () => {
            const hasVisibleRows = Array.from(rows.querySelectorAll('.settlement-row')).some((row) => !row.hidden);
            if (emptyState) emptyState.hidden = hasVisibleRows;
        };

        addButton.dataset.saleRowsBound = 'true';
        rows.addEventListener('click', (event) => {
            const moreButton = event.target.closest('.settlement-more-toggle');
            if (moreButton) {
                const row = moreButton.closest('.settlement-row');
                const expanded = moreButton.getAttribute('aria-expanded') === 'true';
                moreButton.setAttribute('aria-expanded', String(!expanded));
                moreButton.textContent = expanded ? 'Więcej danych' : 'Mniej danych';
                row?.classList.toggle('is-expanded', !expanded);
                return;
            }
            const button = event.target.closest('.remove-settlement-row');
            if (!button) return;
            const row = button.closest('.settlement-row');
            const checkbox = row?.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (checkbox) checkbox.checked = true;
            if (row) row.hidden = true;
            updateEmptyState();
        });
        rows.addEventListener('input', (event) => {
            const input = event.target.closest('input');
            if (!input) return;
            if (/-(avg_weight|net_value|gross_value)$/.test(input.name) && !event.isTrusted) return;
            if (/-(avg_weight|net_value|gross_value)$/.test(input.name)) {
                input.dataset.calculated = 'false';
            }
            calculateRow(input.closest('.settlement-row'));
        });
        addButton.addEventListener('click', () => {
            const index = parseInt(totalForms.value, 10);
            const html = template.innerHTML.replaceAll('__prefix__', index);

            rows.insertAdjacentHTML('beforeend', html);
            totalForms.value = index + 1;

            const newRow = rows.lastElementChild;
            const lineInput = newRow.querySelector('input[name$="-line_no"]');
            if (lineInput && !lineInput.value) {
                lineInput.value = index + 1;
            }

            window.enhanceAutoResizeFields?.(newRow);
            window.enhanceDataTables?.();
            updateEmptyState();
        });
        saleForm?.querySelectorAll('[name="settlement_process"]').forEach((radio) => {
            radio.addEventListener('change', () => {
                const mode = saleForm.querySelector('[name="settlement_process"]:checked')?.value || 'manual';
                saleForm.querySelectorAll('[data-pdf-settlement]').forEach((element) => {
                    element.hidden = mode !== 'pdf';
                });
                const manualPanel = saleForm.querySelector('[data-manual-settlement]');
                if (manualPanel) manualPanel.hidden = mode === 'later';
                const noSettlement = saleForm.querySelector('[name="no_settlement"]');
                if (noSettlement) noSettlement.value = mode === 'later' ? 'True' : 'False';
            });
        });
        saleForm?.querySelector('[name="settlement_process"]:checked')?.dispatchEvent(new Event('change'));
        updateEmptyState();
    }

    function initRecipeFormset(root = document) {
        const form = root.getElementById?.('recipe-form') || document.getElementById('recipe-form');
        if (!form || form.dataset.recipeRowsBound === 'true') return;

        const container = document.getElementById('ingredient-forms-container');
        const totalFormsInput = form.querySelector('input[name$="-TOTAL_FORMS"]');
        const addButton = document.getElementById('add-ingredient-btn');
        const template = document.getElementById('empty-form-template');

        if (!container || !totalFormsInput || !addButton || !template) return;

        form.dataset.recipeRowsBound = 'true';

        const totalElement = document.getElementById('recipe-percentage-total');
        const summaryElement = document.getElementById('recipe-percentage-summary');
        const emptyState = document.getElementById('ingredient-forms-empty');

        const updateEmptyState = () => {
            const hasVisibleRows = Array.from(container.querySelectorAll('.ingredient-row-card')).some((row) => !row.hidden);
            if (emptyState) emptyState.hidden = hasVisibleRows;
        };

        const updatePercentageSummary = () => {
            let total = 0;

            container.querySelectorAll('.ingredient-row-card').forEach((row) => {
                const deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
                if (deleteCheckbox?.checked) return;

                const percentageInput = row.querySelector('input[name$="-percentage"]');
                const value = Number.parseFloat(String(percentageInput?.value || '').replace(',', '.'));
                if (Number.isFinite(value)) total += value;
            });

            if (totalElement) {
                totalElement.textContent = total.toLocaleString('pl-PL', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                });
            }
            if (summaryElement) {
                const isComplete = Math.abs(total - 100) < 0.005;
                summaryElement.classList.toggle('notice-success', isComplete);
                summaryElement.classList.toggle('notice-danger', !isComplete);
            }
        };

        addButton.addEventListener('click', (event) => {
            event.preventDefault();
            const currentFormCount = parseInt(totalFormsInput.value, 10);
            const newRowHtml = template.innerHTML.replace(/__prefix__/g, currentFormCount);

            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = newRowHtml.trim();
            const newRow = tempDiv.firstElementChild;

            container.appendChild(newRow);
            totalFormsInput.value = currentFormCount + 1;
            window.enhanceAutoResizeFields?.(newRow);
            updatePercentageSummary();
            updateEmptyState();
        });

        container.addEventListener('click', (event) => {
            const removeButton = event.target.closest('.remove-row-btn');
            if (!removeButton) return;

            event.preventDefault();
            const row = removeButton.closest('.ingredient-row-card');
            const deleteCheckbox = row?.querySelector('input[type="checkbox"][name$="-DELETE"]');

            if (deleteCheckbox) deleteCheckbox.checked = true;
            if (row) {
                row.hidden = true;
                row.classList.add('hidden');
            }
            updatePercentageSummary();
            updateEmptyState();
        });

        container.addEventListener('input', (event) => {
            if (event.target.matches('input[name$="-percentage"]')) updatePercentageSummary();
        });

        updatePercentageSummary();
        updateEmptyState();
    }

    function initDeliveryFormset(root = document) {
        const form = root.getElementById?.('delivery-form') || document.getElementById('delivery-form');
        if (!form || form.dataset.deliveryRowsBound === 'true') return;

        const rows = document.getElementById('delivery-rows');
        const totalForms = form.querySelector('input[name$="-TOTAL_FORMS"]');
        const template = document.getElementById('delivery-row-template');
        const addButton = document.getElementById('add-delivery-row');
        const emptyState = document.getElementById('delivery-rows-empty');
        if (!rows || !totalForms || !template || !addButton) return;

        const updateEmptyState = () => {
            const hasVisibleRows = Array.from(rows.querySelectorAll('.delivery-row')).some((row) => !row.hidden);
            if (emptyState) emptyState.hidden = hasVisibleRows;
        };

        form.dataset.deliveryRowsBound = 'true';
        rows.addEventListener('click', (event) => {
            const button = event.target.closest('.remove-delivery-row');
            if (!button) return;

            const row = button.closest('.delivery-row');
            const deleteCheckbox = row?.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (deleteCheckbox) deleteCheckbox.checked = true;
            if (row) row.hidden = true;
            updateEmptyState();
        });

        addButton.addEventListener('click', () => {
            const index = parseInt(totalForms.value, 10);
            const html = template.innerHTML.replaceAll('__prefix__', index);
            rows.insertAdjacentHTML('beforeend', html);
            totalForms.value = index + 1;
            window.enhanceAutoResizeFields?.(rows.lastElementChild);
            updateEmptyState();
        });

        updateEmptyState();
    }

    function initProductionStageChecklist(root = document) {
        const form = root.getElementById?.('stageForm') || document.getElementById('stageForm');
        if (!form || form.dataset.stageChecklistBound === 'true') return;

        const storageKey = form.dataset.stageStorageKey;
        if (!storageKey) return;

        let checkedState = parseJson(localStorage.getItem(storageKey), {});
        const checkboxes = Array.from(document.querySelectorAll('.ingredient-checkbox[form="stageForm"]'));
        const submitButton = form.querySelector('[data-stage-submit]');
        const checkAllButton = document.querySelector('[data-check-all-ingredients]');

        const toggleRowStyle = (checkbox) => {
            const row = checkbox.closest('.ingredient-row');
            const nameText = row?.querySelector('.row-name');

            row?.classList.toggle('is-complete', checkbox.checked);
            nameText?.classList.toggle('line-through', checkbox.checked);
            nameText?.classList.toggle('is-complete', checkbox.checked);
        };
        const updateCompletion = () => {
            const complete = checkboxes.every((checkbox) => checkbox.checked);
            if (submitButton) submitButton.disabled = !complete;
            if (checkAllButton) {
                checkAllButton.textContent = complete ? 'Odznacz wszystkie' : 'Zaznacz wszystkie';
                checkAllButton.setAttribute('aria-pressed', String(complete));
            }
        };

        form.dataset.stageChecklistBound = 'true';
        checkboxes.forEach((checkbox) => {
            const itemId = checkbox.dataset.id;
            checkbox.checked = Boolean(checkedState[itemId]);
            toggleRowStyle(checkbox);

            checkbox.addEventListener('change', function () {
                checkedState[itemId] = this.checked;
                localStorage.setItem(storageKey, JSON.stringify(checkedState));
                toggleRowStyle(this);
                updateCompletion();
            });
        });
        checkAllButton?.addEventListener('click', () => {
            const shouldCheck = !checkboxes.every((checkbox) => checkbox.checked);
            checkboxes.forEach((checkbox) => {
                checkbox.checked = shouldCheck;
                checkedState[checkbox.dataset.id] = shouldCheck;
                toggleRowStyle(checkbox);
            });
            localStorage.setItem(storageKey, JSON.stringify(checkedState));
            updateCompletion();
        });

        form.addEventListener('submit', () => {
            localStorage.removeItem(storageKey);
        });
        updateCompletion();
    }

    function initConfirmations(root = document) {
        root.querySelectorAll('[data-confirm]').forEach((element) => {
            if (element.dataset.confirmBound === 'true') return;

            element.dataset.confirmBound = 'true';
            const eventName = element.tagName === 'FORM' ? 'submit' : 'click';

            element.addEventListener(eventName, (event) => {
                if (element.dataset.submitting === 'true') {
                    event.preventDefault();
                    return;
                }
                const message = element.dataset.confirm;
                if (message && !window.confirm(message)) {
                    event.preventDefault();
                    return;
                }

                if (element.tagName === 'FORM') {
                    const submitter = event.submitter || element.querySelector('[type="submit"]');
                    const pendingLabel = element.dataset.submitLabel || (
                        /usuń|usunąć|usunię/i.test(`${message || ''} ${submitter?.textContent || ''}`)
                            ? 'Usuwanie…'
                            : 'Przetwarzanie…'
                    );
                    element.dataset.submitting = 'true';
                    element.setAttribute('aria-busy', 'true');
                    if (submitter) {
                        submitter.dataset.originalLabel = submitter.textContent;
                        submitter.textContent = pendingLabel;
                        submitter.classList.add('is-submitting');
                        submitter.disabled = true;
                    }
                }
            });
        });
    }

    function resetPendingConfirmations(root = document) {
        root.querySelectorAll('form[data-submitting="true"]').forEach((form) => {
            form.dataset.submitting = 'false';
            form.removeAttribute('aria-busy');
            form.querySelectorAll('[data-original-label]').forEach((button) => {
                button.textContent = button.dataset.originalLabel;
                delete button.dataset.originalLabel;
                button.classList.remove('is-submitting');
                button.disabled = false;
            });
        });
    }

    function initNotificationCenter(root = document) {
        const center = root.querySelector('[data-notification-center]');
        if (!center || center.dataset.notificationBound === 'true') return;

        const dialog = center.querySelector('[data-notification-dialog]');
        const title = center.querySelector('[data-notification-title]');
        const message = center.querySelector('[data-notification-message]');
        const confirmButton = center.querySelector('[data-notification-confirm]');
        const timerBar = center.querySelector('.notification-timer');
        if (!dialog || !title || !message || !confirmButton) return;

        const typeSettings = {
            success: {
                title: 'Operacja zakończona pomyślnie',
                timeout: Number(center.dataset.successTimeout) || 3200
            },
            info: {
                title: 'Informacja',
                timeout: Number(center.dataset.infoTimeout) || 4500
            },
            warning: {
                title: 'Wymagana uwaga',
                timeout: Number(center.dataset.warningTimeout) || 6000
            },
            error: {
                title: 'Nie udało się wykonać operacji',
                timeout: Number(center.dataset.errorTimeout) || 8000
            }
        };
        const normalizeText = (value) => value.replace(/\s+/g, ' ').trim();
        const entries = [];
        const seen = new Set();

        const addEntry = (element, origin) => {
            const text = normalizeText(element.textContent || '');
            if (!text) return;

            const requestedType = element.dataset.notificationType || 'success';
            const type = typeSettings[requestedType] ? requestedType : 'success';
            const entryTitle = normalizeText(element.dataset.notificationTitle || '');
            const key = `${type}:${entryTitle}:${text}`;
            if (seen.has(key)) return;

            seen.add(key);
            entries.push({
                type,
                title: entryTitle,
                text,
                origin,
                persistent: element.dataset.notificationPersistent === 'true'
            });
        };

        center.querySelectorAll('[data-notification-entry]').forEach((element) => addEntry(element, 'message'));
        root.querySelectorAll('[data-notification-source]').forEach((element) => addEntry(element, 'form'));

        const inlineErrorDetails = [];
        root.querySelectorAll('.errorlist').forEach((errorList) => {
            if (errorList.closest('[data-notification-source]')) return;

            const container = errorList.closest('.form-field, td');
            const label = normalizeText(
                container?.querySelector('label')?.textContent || container?.dataset.label || ''
            );
            const errors = Array.from(errorList.querySelectorAll('li'));
            const errorTexts = errors.length ? errors : [errorList];

            errorTexts.forEach((error) => {
                const errorText = normalizeText(error.textContent || '');
                if (!errorText) return;
                const detail = label ? `${label}: ${errorText}` : errorText;
                if (!inlineErrorDetails.includes(detail)) inlineErrorDetails.push(detail);
            });
        });

        if (inlineErrorDetails.length) {
            const visibleDetails = inlineErrorDetails.slice(0, 4).map((detail) => `• ${detail}`);
            if (inlineErrorDetails.length > visibleDetails.length) {
                visibleDetails.push(`• Pozostałe błędy: ${inlineErrorDetails.length - visibleDetails.length}.`);
            }
            const detailText = visibleDetails.join('\n');
            const formEntry = entries.find((entry) => entry.origin === 'form' && entry.type === 'error');

            if (formEntry) {
                formEntry.text = `${formEntry.text}\n${detailText}`;
            } else {
                entries.push({
                    type: 'error',
                    title: 'Nie zapisano zmian',
                    text: `Popraw oznaczone pola.\n${detailText}`,
                    origin: 'form',
                    persistent: false
                });
            }
        }

        if (!entries.length) return;

        center.dataset.notificationBound = 'true';
        let activeIndex = -1;
        let closeTimer = null;
        let nextTimer = null;
        let isClosing = false;
        const previouslyFocused = document.activeElement;

        const finishQueue = () => {
            center.hidden = true;
            document.body.classList.remove('notification-open');
            if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
                previouslyFocused.focus({ preventScroll: true });
            }
        };

        const showNext = () => {
            activeIndex += 1;
            const entry = entries[activeIndex];
            if (!entry) {
                finishQueue();
                return;
            }

            const settings = typeSettings[entry.type];
            const timeout = entry.persistent ? null : settings.timeout;
            isClosing = false;
            dialog.dataset.type = entry.type;
            dialog.dataset.persistent = timeout ? 'false' : 'true';
            if (timeout) {
                dialog.style.setProperty('--notification-timeout', `${timeout}ms`);
            } else {
                dialog.style.removeProperty('--notification-timeout');
            }
            title.textContent = entry.title || settings.title;
            message.textContent = entry.text;
            center.hidden = false;
            document.body.classList.add('notification-open');

            if (timerBar) {
                timerBar.style.animation = 'none';
                if (timeout) {
                    void timerBar.offsetWidth;
                    timerBar.style.animation = '';
                }
            }

            window.requestAnimationFrame(() => confirmButton.focus({ preventScroll: true }));
            closeTimer = timeout
                ? window.setTimeout(closeCurrent, timeout)
                : null;
        };

        const closeCurrent = () => {
            if (isClosing) return;
            isClosing = true;
            window.clearTimeout(closeTimer);
            center.hidden = true;
            document.body.classList.remove('notification-open');

            if (activeIndex < entries.length - 1) {
                nextTimer = window.setTimeout(showNext, 150);
            } else {
                finishQueue();
            }
        };

        confirmButton.addEventListener('click', closeCurrent);
        center.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && dialog.dataset.persistent !== 'true') {
                event.preventDefault();
                closeCurrent();
            }
            if (event.key === 'Tab') {
                event.preventDefault();
                confirmButton.focus();
            }
        });
        window.addEventListener('pagehide', () => {
            window.clearTimeout(closeTimer);
            window.clearTimeout(nextTimer);
        }, { once: true });

        showNext();
    }

    function initDisclosureMenus(root = document) {
        const menus = Array.from(root.querySelectorAll('.account-menu, .notification-menu, [data-mobile-search]'));
        if (!menus.length) return;

        document.addEventListener('click', (event) => {
            menus.forEach((menu) => {
                if (!menu.contains(event.target)) menu.removeAttribute('open');
            });
        });

        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            menus.forEach((menu) => {
                if (!menu.open) return;
                menu.removeAttribute('open');
                menu.querySelector('summary')?.focus();
            });
        });

        root.querySelectorAll('[data-mobile-search]').forEach((menu) => {
            const input = menu.querySelector('input[type="search"]');
            menu.addEventListener('toggle', () => {
                if (menu.open) window.requestAnimationFrame(() => input?.focus());
            });
            menu.querySelectorAll('[data-mobile-search-close]').forEach((button) => {
                button.addEventListener('click', () => {
                    menu.removeAttribute('open');
                    menu.querySelector('summary')?.focus();
                });
            });
        });
    }

    function initFormAccessibility(root = document) {
        root.querySelectorAll('[data-form-field]').forEach((container) => {
            const field = container.querySelector('input, select, textarea');
            if (!field) return;
            const describedBy = [
                container.querySelector('.field-hint')?.id,
                container.querySelector('.field-error')?.id
            ].filter(Boolean);
            if (describedBy.length) field.setAttribute('aria-describedby', describedBy.join(' '));
            if (container.classList.contains('has-error')) field.setAttribute('aria-invalid', 'true');
        });

        const summary = root.querySelector('[data-form-error-summary]');
        if (!summary) return;
        const firstError = root.querySelector(
            '.has-error input, .has-error select, .has-error textarea, '
            + '.form-field .errorlist'
        );
        const firstField = firstError?.matches('input, select, textarea')
            ? firstError
            : firstError?.closest('.form-field')?.querySelector('input, select, textarea');
        window.requestAnimationFrame(() => {
            (firstField || summary).focus({ preventScroll: true });
            (firstField || summary).scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    }

    function initPriceUnitToggles(root = document) {
        root.querySelectorAll('[data-price-unit-toggle]').forEach((toggle) => {
            if (toggle.dataset.priceUnitBound === 'true') return;

            const scopeSelector = toggle.dataset.priceUnitScope;
            const scope = scopeSelector ? document.querySelector(scopeSelector) : toggle.closest('[data-price-unit-scope]');
            if (!scope) return;

            toggle.dataset.priceUnitBound = 'true';
            const buttons = Array.from(toggle.querySelectorAll('[data-price-unit]'));
            const storageKey = toggle.dataset.priceUnitStorage || 'feed-price-unit';

            const applyUnit = (unit) => {
                const safeUnit = unit === 'kg' ? 'kg' : 'ton';
                scope.querySelectorAll('[data-price-kg][data-price-ton]').forEach((element) => {
                    element.textContent = safeUnit === 'kg' ? element.dataset.priceKg : element.dataset.priceTon;
                });
                scope.querySelectorAll('[data-price-unit-label]').forEach((element) => {
                    element.textContent = safeUnit === 'kg' ? 'PLN/kg' : 'PLN/t';
                });
                buttons.forEach((button) => {
                    const isActive = button.dataset.priceUnit === safeUnit;
                    button.classList.toggle('is-active', isActive);
                    button.setAttribute('aria-pressed', String(isActive));
                });
                localStorage.setItem(storageKey, safeUnit);
            };

            buttons.forEach((button) => {
                button.addEventListener('click', () => applyUnit(button.dataset.priceUnit));
            });

            applyUnit(localStorage.getItem(storageKey) || toggle.dataset.defaultPriceUnit || 'ton');
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        initNotificationCenter();
        initDateRangeFilters();
        initSingleSowEventForm();
        initBulkEventForm();
        initMortalityForm();
        initVaccinationPlanForm();
        initTodayTaskForms();
        initTodayTaskDialogs();
        initSaleFormset();
        initRecipeFormset();
        initDeliveryFormset();
        initProductionStageChecklist();
        initConfirmations();
        initDisclosureMenus();
        initFormAccessibility();
        initPriceUnitToggles();
        initTrendCharts();
    });
    window.addEventListener('pageshow', () => resetPendingConfirmations());
})();

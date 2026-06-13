(function () {
    "use strict";

    function hasResponsiveWrapper(element) {
        return element.parentElement && (
            element.parentElement.classList.contains("data-table-scroll") ||
            element.parentElement.classList.contains("overflow-x-auto")
        );
    }

    function enhanceTable(table) {
        if (table.dataset.enhanced === "true") {
            return;
        }

        table.dataset.enhanced = "true";
        table.classList.add("app-table");

        if (!hasResponsiveWrapper(table)) {
            const wrapper = document.createElement("div");
            wrapper.className = "data-table-scroll";
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        }

        const shell = table.closest(".bg-white, .table-card");
        if (shell) {
            shell.classList.add("table-card");
        }

        const headers = Array.from(table.querySelectorAll("thead th")).map((header) =>
            header.textContent.trim()
        );

        table.querySelectorAll("tbody tr").forEach((row) => {
            Array.from(row.children).forEach((cell, index) => {
                if (headers[index] && !cell.dataset.label) {
                    cell.dataset.label = headers[index];
                }
            });
        });
    }

    function enhanceTables() {
        document.querySelectorAll("table").forEach(enhanceTable);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", enhanceTables);
    } else {
        enhanceTables();
    }
})();

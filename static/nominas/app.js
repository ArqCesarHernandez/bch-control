(() => {
  "use strict";

  const money = value => Number(value || 0);
  // Replica el redondeo monetario a centavos que hace Python en el servidor.
  const roundMoney = value => Math.round((Number(value || 0) + Number.EPSILON) * 100) / 100;
  const currency = value => new Intl.NumberFormat("es-MX", {
    style: "currency", currency: "MXN", minimumFractionDigits: 2
  }).format(Number(value || 0));

  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // Carga partidas según la obra seleccionada en formularios de altas/pagos.
  document.querySelectorAll("select[data-project-select]").forEach(projectSelect => {
    const target = document.getElementById(projectSelect.dataset.projectSelect);
    if (!target) return;
    const selectedItem = target.dataset.selected || "";
    const category = target.dataset.category || "";
    const loadItems = async () => {
      const projectId = projectSelect.value;
      target.innerHTML = '<option value="">Selecciona una partida</option>';
      if (!projectId) return;
      target.disabled = true;
      try {
        const suffix = category ? `?categoria=${encodeURIComponent(category)}` : "";
        const response = await fetch(`/api/obras/${projectId}/partidas${suffix}`, {credentials: "same-origin"});
        if (!response.ok) throw new Error("No fue posible cargar las partidas");
        const items = await response.json();
        items.forEach(item => {
          const option = new Option(`${item.label} · ${item.category}`, String(item.id));
          if (String(item.id) === String(selectedItem)) option.selected = true;
          target.add(option);
        });
      } catch (error) {
        target.add(new Option("Error al cargar partidas", ""));
      } finally {
        target.disabled = false;
      }
    };
    projectSelect.addEventListener("change", loadItems);
    if (projectSelect.value && target.options.length <= 1) loadItems();
  });

  // Partida y subpartida dependen de la obra de la nómina y se guardan por
  // línea. La validación se replica en backend para impedir manipulaciones.
  const payrollForm = document.getElementById("payroll-form");
  const allocationError = document.getElementById("payroll-allocation-error");
  const showAllocationError = control => {
    if (allocationError) {
      allocationError.classList.remove("d-none");
      allocationError.scrollIntoView({behavior: "smooth", block: "center"});
    }
    if (control) control.focus({preventScroll: true});
  };
  const invalidAllocation = () => {
    const partida = [...document.querySelectorAll(".payroll-partida-select")]
      .find(select => !select.value);
    if (partida) return partida;
    return [...document.querySelectorAll(".payroll-subpartida-select")]
      .find(select => !select.disabled && !select.value);
  };

  document.querySelectorAll(".payroll-partida-select").forEach(partidaSelect => {
    const subpartidaSelect = document.getElementById(
      partidaSelect.dataset.subpartidaTarget
    );
    if (!subpartidaSelect) return;
    const initialSelected = String(subpartidaSelect.dataset.selected || "");
    const subpartidas = [...subpartidaSelect.querySelectorAll("option[data-parent-id]")]
      .map(option => ({
        parentId: String(option.dataset.parentId),
        value: String(option.value),
        label: option.textContent
      }));

    const renderSubpartidas = preserveSelection => {
      const previous = preserveSelection
        ? String(subpartidaSelect.value || initialSelected)
        : "";
      const available = subpartidas.filter(
        option => option.parentId === String(partidaSelect.value)
      );
      subpartidaSelect.replaceChildren(
        new Option(
          available.length ? "Selecciona subpartida" : "No aplica",
          ""
        )
      );
      available.forEach(option => {
        const element = new Option(option.label, option.value);
        element.dataset.parentId = option.parentId;
        element.selected = option.value === previous;
        subpartidaSelect.add(element);
      });
      subpartidaSelect.disabled = available.length === 0;
      subpartidaSelect.required = available.length > 0;
      subpartidaSelect.setCustomValidity("");
    };

    partidaSelect.addEventListener("change", () => {
      partidaSelect.setCustomValidity("");
      renderSubpartidas(false);
      if (!invalidAllocation() && allocationError) {
        allocationError.classList.add("d-none");
      }
    });
    subpartidaSelect.addEventListener("change", () => {
      subpartidaSelect.setCustomValidity("");
      if (!invalidAllocation() && allocationError) {
        allocationError.classList.add("d-none");
      }
    });
    renderSubpartidas(true);
  });

  if (payrollForm) {
    payrollForm.addEventListener("invalid", event => {
      if (
        event.target.matches(
          ".payroll-partida-select, .payroll-subpartida-select"
        )
      ) {
        event.target.setCustomValidity(
          "Debe asignar una partida a cada trabajador antes de guardar."
        );
        showAllocationError(event.target);
      }
    }, true);
    payrollForm.addEventListener("submit", event => {
      const invalid = invalidAllocation();
      if (invalid) {
        event.preventDefault();
        invalid.setCustomValidity(
          "Debe asignar una partida a cada trabajador antes de guardar."
        );
        invalid.reportValidity();
        showAllocationError(invalid);
      }
    });
  }

  // Vista previa inmediata de cada línea de nómina. El servidor vuelve a validar todo.
  document.querySelectorAll(".payroll-row").forEach(row => {
    const get = suffix => row.querySelector(`[data-field="${suffix}"]`);
    const output = suffix => row.querySelector(`[data-output="${suffix}"]`);
    const recalc = () => {
      const weekly = roundMoney(money(get("salario")?.value));
      const days = [...row.querySelectorAll('[data-field="attendance"]')].filter(input => input.checked).length;
      const daily = roundMoney(weekly / 5);
      const gross = roundMoney(daily * days);
      const absence = roundMoney(weekly - gross);
      const extra = roundMoney(money(get("extra")?.value));
      const infonavit = roundMoney(money(get("infonavit")?.value));
      const imssEnabled = row.dataset.imssEnabled === "1";
      const imssValue = money(row.dataset.imssValue);
      const imss = roundMoney(!imssEnabled ? 0 : row.dataset.imssType === "PORCENTAJE"
        ? gross * imssValue / 100
        : imssValue);
      const other = roundMoney(money(get("other")?.value));
      const loan = roundMoney(money(row.dataset.loan));
      // El sueldo es libre: IMSS es costo patronal y no reduce el neto.
      const beforeLoan = Math.max(0, roundMoney(gross + extra - infonavit - other));
      const appliedLoan = roundMoney(Math.min(loan, beforeLoan));
      const net = Math.max(0, roundMoney(beforeLoan - appliedLoan));
      const transferInput = get("transfer");
      let transfer = roundMoney(money(transferInput?.value));
      if (transfer > net) transfer = net;
      const cash = roundMoney(net - transfer);
      if (output("days")) output("days").textContent = days;
      if (output("absences")) output("absences").textContent = 5 - days;
      if (output("daily")) output("daily").textContent = currency(daily);
      if (output("absence")) output("absence").textContent = currency(absence);
      if (output("gross")) output("gross").textContent = currency(gross);
      if (output("imss")) output("imss").textContent = currency(imss);
      if (output("loan")) output("loan").textContent = currency(appliedLoan);
      if (output("net")) output("net").textContent = currency(net);
      if (output("cash")) output("cash").textContent = currency(cash);
      if (transferInput) {
        transferInput.max = net.toFixed(2);
        const enteredTransfer = money(transferInput.value);
        transferInput.setCustomValidity(
          enteredTransfer > net
            ? `La transferencia ${currency(enteredTransfer)} supera el neto actual ${currency(net)}. Revisa el préstamo automático.`
            : ""
        );
      }
    };
    row.querySelectorAll("input, select").forEach(input => input.addEventListener("input", recalc));
    recalc();
  });

  // Bootstrap valida los formularios marcados sin enviarlos incompletos.
  document.querySelectorAll(".needs-validation").forEach(form => {
    form.addEventListener("submit", event => {
      if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
      }
      form.classList.add("was-validated");
    });
  });
})();

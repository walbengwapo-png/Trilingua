/** Display formulas honestly when no calculated result was saved by Excel. */
export function renderWorkbook(XLSX, workbook) {
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    if (!sheet) return '<p>The workbook has no sheets.</p>';
    const display = { ...sheet };
    let missingResults = false;
    for (const [address, cell] of Object.entries(sheet)) {
        if (!address.startsWith('!') && cell && cell.f && cell.v == null) {
            display[address] = { ...cell, t: 's', v: '=' + cell.f };
            delete display[address].w;
            delete display[address].h;
            missingResults = true;
        }
    }
    const notice = missingResults
        ? '<p>Some formulas have no calculated result yet. Formulas are shown; open and recalculate the workbook in Excel to see results.</p>'
        : '';
    return notice + XLSX.utils.sheet_to_html(display, { header: '', footer: '' });
}

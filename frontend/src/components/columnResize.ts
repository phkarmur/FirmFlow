/**
 * Column resize for every table that has a <thead> with <th> cells.
 *
 * - A thin vertical bar is put on the right edge of each header cell. Drag it to change the column width.
 * - Double-click the bar to go back to the automatic widths.
 * - Widths are kept per page and per table header (browser localStorage, this browser only).
 *
 * This works on the DOM (MutationObserver), so all present and future tables get it without changes
 * in each page. Tables can opt out with the attribute data-no-col-resize.
 *
 * Logs (browser console): "[colresize] ..." at debug level for apply / save / reset.
 */
const MIN_W = 48;
const KEY_PREFIX = 'ff.colw:';

const headerCells = (table: HTMLTableElement): HTMLTableCellElement[] => {
  const rows = table.tHead?.rows;
  if (!rows || rows.length === 0) return [];
  return Array.from(rows[rows.length - 1].cells).filter(c => c.tagName === 'TH') as HTMLTableCellElement[];
};

// The header text identifies the table layout. When the columns change, the saved widths are not used.
const signature = (cells: HTMLTableCellElement[]) =>
  cells.map(c => (c.textContent || '').trim().toLowerCase().slice(0, 30)).join('|');

const storageKey = (table: HTMLTableElement, sig: string) => {
  const all = Array.from(document.querySelectorAll('table'));
  return `${KEY_PREFIX}${window.location.pathname}:${all.indexOf(table)}:${sig}`;
};

const readSaved = (key: string): number[] | null => {
  try {
    const v = JSON.parse(window.localStorage.getItem(key) || 'null');
    return Array.isArray(v) ? v : null;
  } catch { return null; }
};
const writeSaved = (key: string, widths: number[] | null) => {
  try {
    if (widths) window.localStorage.setItem(key, JSON.stringify(widths));
    else window.localStorage.removeItem(key);
  } catch (e) { console.debug('[colresize] storage not available', e); }
};

const clearSizes = (table: HTMLTableElement, cells: HTMLTableCellElement[]) => {
  table.classList.remove('ff-col-resized');
  table.style.tableLayout = '';
  table.style.minWidth = '';
  cells.forEach(c => { c.style.width = ''; });
};

const applySizes = (table: HTMLTableElement, cells: HTMLTableCellElement[], widths: number[]) => {
  cells.forEach((c, i) => { c.style.width = `${Math.max(MIN_W, widths[i])}px`; });
  // The table stays at least 100% wide (Tailwind w-full); when the columns are wider, the
  // scroll container around the table scrolls sideways.
  table.style.minWidth = `${widths.reduce((a, b) => a + Math.max(MIN_W, b), 0)}px`;
  table.style.tableLayout = 'fixed';
  table.classList.add('ff-col-resized');
};

const enhanceTable = (table: HTMLTableElement) => {
  if (table.hasAttribute('data-no-col-resize')) return;
  const cells = headerCells(table);
  if (cells.length === 0) return;
  const sig = signature(cells);
  if (table.dataset.colSig !== sig) {
    // New table, or the columns changed (for example another report): start from the saved widths or auto.
    const hadSig = table.dataset.colSig !== undefined;
    table.dataset.colSig = sig;
    clearSizes(table, cells);
    const saved = readSaved(storageKey(table, sig));
    if (saved && saved.length === cells.length) {
      applySizes(table, cells, saved);
      console.debug('[colresize] applied saved widths', { path: window.location.pathname, columns: cells.length });
    } else if (hadSig) {
      console.debug('[colresize] columns changed, auto widths', { path: window.location.pathname });
    }
  }
  cells.forEach((th, index) => {
    if (th.querySelector(':scope > .ff-col-handle')) return;
    if (getComputedStyle(th).position === 'static') th.style.position = 'relative';
    const handle = document.createElement('span');
    handle.className = 'ff-col-handle';
    handle.setAttribute('role', 'separator');
    handle.setAttribute('aria-orientation', 'vertical');
    handle.title = 'Drag to resize the column. Double-click to reset.';
    handle.addEventListener('click', e => e.stopPropagation());
    handle.addEventListener('dblclick', e => {
      e.preventDefault(); e.stopPropagation();
      const now = headerCells(table);
      clearSizes(table, now);
      writeSaved(storageKey(table, signature(now)), null);
      console.debug('[colresize] reset to auto widths', { path: window.location.pathname });
    });
    handle.addEventListener('pointerdown', e => {
      e.preventDefault(); e.stopPropagation();
      const now = headerCells(table);
      const col = now.indexOf(th);
      if (col < 0) return;
      // Freeze the present widths, then change only the dragged column
      const widths = now.map(c => c.getBoundingClientRect().width);
      applySizes(table, now, widths);
      const startX = e.clientX;
      const startW = widths[col];
      handle.classList.add('is-dragging');
      handle.setPointerCapture(e.pointerId);
      const prevSelect = document.body.style.userSelect;
      document.body.style.userSelect = 'none';
      const move = (ev: PointerEvent) => {
        widths[col] = Math.max(MIN_W, Math.round(startW + ev.clientX - startX));
        applySizes(table, now, widths);
      };
      const up = () => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', up);
        handle.removeEventListener('pointercancel', up);
        handle.classList.remove('is-dragging');
        document.body.style.userSelect = prevSelect;
        writeSaved(storageKey(table, signature(now)), widths);
        console.debug('[colresize] saved widths', { path: window.location.pathname, column: col, width: widths[col] });
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', up);
      handle.addEventListener('pointercancel', up);
    });
    th.appendChild(handle);
    void index;
  });
};

let started = false;
export const enableColumnResize = (): (() => void) => {
  if (started) return () => {};
  started = true;
  let scheduled = false;
  const scan = () => {
    scheduled = false;
    document.querySelectorAll('table').forEach(t => enhanceTable(t as HTMLTableElement));
  };
  const observer = new MutationObserver(() => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(scan); }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  scan();
  console.debug('[colresize] enabled');
  return () => { observer.disconnect(); started = false; };
};
